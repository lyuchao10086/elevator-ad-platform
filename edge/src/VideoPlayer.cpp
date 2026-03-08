#include "VideoPlayer.hpp"
#include <iostream>
#include <thread>
#include <atomic>
#include <chrono>
#include <queue>
#include <mutex>
#include <condition_variable>

// PIMPL模式实现
struct VideoPlayer::Impl {
    // FFmpeg上下文
    AVFormatContext* format_ctx = nullptr;
    AVCodecContext* video_codec_ctx = nullptr;
    AVStream* video_stream = nullptr;
    SwsContext* sws_ctx = nullptr;

    // SDL上下文
    SDL_Window* window = nullptr;
    SDL_Renderer* renderer = nullptr;
    SDL_Texture* texture = nullptr;

    // 帧队列
    struct Frame {
        std::unique_ptr<uint8_t[]> data;
        int width, height;
        int64_t pts;  // 显示时间戳
        ~Frame() = default;
    };

    std::queue<std::unique_ptr<Frame>> frame_queue;
    std::mutex queue_mutex;
    std::condition_variable queue_cv;
    const size_t MAX_QUEUE_SIZE = 10;  // 限制队列大小，避免内存爆炸

    // 播放状态
    std::atomic<bool> is_playing{ false };
    std::atomic<bool> is_paused{ false };
    std::atomic<bool> should_stop{ false };
    std::atomic<bool> window_open{ false };

    // 视频信息
    int video_stream_index = -1;
    int width = 0;
    int height = 0;
    double frame_rate = 0.0;
    int64_t duration_ms = 0;
    int64_t target_duration_ms = 0; // 目标播放时长
    bool is_image = false;          // 是否为图片模式
    std::string current_title;      // 当前标题
    std::chrono::steady_clock::time_point playback_start_time;
    AVRational time_base;

    // 线程
    std::unique_ptr<std::thread> decode_thread;
    
    // 渲染控制
    std::chrono::steady_clock::time_point last_render_time;

    // 回调函数
    VideoPlayer::FrameCallback frame_callback;

    ~Impl() {
        CleanupAll();
    }

    void CleanupAll() {
        CleanupDecoder();
        CleanupSDL();
    }

    void CleanupDecoder() {
        std::cout << "[VideoPlayer] CleanupDecoder: 开始清理" << std::endl;
        should_stop = true;

        // 唤醒等待的线程
        queue_cv.notify_all();
        std::cout << "[VideoPlayer] CleanupDecoder: 已发送 notify_all" << std::endl;

        // 等待线程结束
        if (decode_thread && decode_thread->joinable()) {
            std::cout << "[VideoPlayer] CleanupDecoder: 等待解码线程 join..." << std::endl;
            decode_thread->join();
            std::cout << "[VideoPlayer] CleanupDecoder: 解码线程 join 完成" << std::endl;
        }
        
        if (decode_thread) {
            decode_thread.reset();
        }

        // 清理FFmpeg
        std::cout << "[VideoPlayer] CleanupDecoder: 清理 FFmpeg 资源" << std::endl;
        if (sws_ctx) {
            sws_freeContext(sws_ctx);
            sws_ctx = nullptr;
        }
        if (video_codec_ctx) {
            avcodec_free_context(&video_codec_ctx);
        }
        if (format_ctx) {
            avformat_close_input(&format_ctx);
        }

        // 清空队列
        {
            std::lock_guard<std::mutex> lock(queue_mutex);
            std::cout << "[VideoPlayer] CleanupDecoder: 清空队列, 当前大小: " << frame_queue.size() << std::endl;
            while (!frame_queue.empty()) {
                frame_queue.pop();
            }
        }
        
        // 重置状态
        is_playing = false;
        is_paused = false;
        is_image = false;
        std::cout << "[VideoPlayer] CleanupDecoder: 清理完成" << std::endl;
    }

    void CleanupSDL() {
        if (texture) {
            SDL_DestroyTexture(texture);
            texture = nullptr;
        }
        if (renderer) {
            SDL_DestroyRenderer(renderer);
            renderer = nullptr;
        }
        if (window) {
            SDL_DestroyWindow(window);
            window = nullptr;
        }
        window_open = false;
    }

    void CreateSDLWindow(const std::string& title) {
        if (window) {
            // 如果窗口已存在，只更新标题
            SetTitle(title);
            return;
        }
        
        // 设置渲染驱动为 OpenGL，解决 macOS Metal 驱动可能的绿屏和 AGX 警告问题
        SDL_SetHint(SDL_HINT_RENDER_DRIVER, "opengl");

        // 确保SDL已初始化
        if (SDL_Init(SDL_INIT_VIDEO) < 0) {
             std::cerr << "SDL初始化失败: " << SDL_GetError() << std::endl;
             return;
        }

        window = SDL_CreateWindow(title.c_str(),
            SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
            width, height,
            SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE);

        if (!window) {
            std::cerr << "创建SDL窗口失败: " << SDL_GetError() << std::endl;
            return;
        }

        renderer = SDL_CreateRenderer(window, -1,
            SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);

        if (!renderer) {
            std::cerr << "创建SDL渲染器失败: " << SDL_GetError() << std::endl;
            return;
        }

        CreateTexture();

        window_open = true;
        current_title = title;
        std::cout << "SDL窗口创建成功: " << width << "x" << height << std::endl;
    }

    void CreateTexture() {
        if (texture) {
            SDL_DestroyTexture(texture);
        }
        // 创建纹理（YUV420P格式）
        // 改用标准的 SDL_PIXELFORMAT_IYUV，对应 FFmpeg 的 AV_PIX_FMT_YUV420P
        // Planar mode: Y + U + V (3 planes)
        texture = SDL_CreateTexture(renderer,
            SDL_PIXELFORMAT_IYUV, 
            SDL_TEXTUREACCESS_STREAMING,
            width, height);

        if (!texture) {
            std::cerr << "创建SDL纹理失败: " << SDL_GetError() << std::endl;
        }
    }

    void SetTitle(const std::string& title) {
        if (window) {
            SDL_SetWindowTitle(window, title.c_str());
            current_title = title;
        }
    }

    // 解码线程函数
    // 独立线程，负责从文件读取 Packet 并解码为 Frame，放入 frame_queue
    void DecodeThreadFunc() {
        AVPacket* packet = av_packet_alloc();
        AVFrame* frame = av_frame_alloc();

        std::cout << "解码线程启动" << std::endl;
        
        // 关键：确保宽度和高度是偶数（YUV420P要求）
        // 如果是奇数，可能会导致渲染时出现花屏或倾斜
        int target_width = (video_codec_ctx->width + 1) & ~1;  // 对齐到偶数
        int target_height = (video_codec_ctx->height + 1) & ~1;

        // 创建SWS上下文 (用于格式转换和缩放)
        // 将源格式转换为 AV_PIX_FMT_YUV420P，这是 SDL 渲染最通用的格式
        sws_ctx = sws_getContext(
            video_codec_ctx->width, video_codec_ctx->height, video_codec_ctx->pix_fmt,
            target_width, target_height, AV_PIX_FMT_YUV420P,
            SWS_BICUBIC, nullptr, nullptr, nullptr);

        if (!sws_ctx) {
            std::cerr << "无法创建SWS上下文" << std::endl;
            av_packet_free(&packet);
            av_frame_free(&frame);
            return;
        }

        // 创建目标帧 (YUV420P)
        AVFrame* yuv_frame = av_frame_alloc();
        yuv_frame->format = AV_PIX_FMT_YUV420P;
        yuv_frame->width = target_width;
        yuv_frame->height = target_height;

        int align = 32;
        if (av_frame_get_buffer(yuv_frame, align) < 0) {
            std::cerr << "无法分配帧缓冲区" << std::endl;
            av_frame_free(&yuv_frame);
            av_packet_free(&packet);
            av_frame_free(&frame);
            return;
        }

        int frame_count = 0;

        // 解码循环
        while (!should_stop) {
            // 检查是否达到目标时长
            // 如果外部设定了 duration_ms，则强制在此处截断
            if (target_duration_ms > 0) {
                auto now = std::chrono::steady_clock::now();
                int64_t elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - playback_start_time).count();
                if (elapsed >= target_duration_ms) {
                    std::cout << "达到目标播放时长 (" << target_duration_ms << "ms)，停止播放" << std::endl;
                    should_stop = true;
                    break;
                }
            }

            if (is_paused) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }

            // 如果是图片且已经解码了一帧，就不再读取，而是维持显示直到超时
            if (is_image && frame_count >= 1) {
                // 必须周期性检查 should_stop，而不是简单 sleep
                for (int i = 0; i < 10; i++) {
                     if (should_stop) break;
                     std::this_thread::sleep_for(std::chrono::milliseconds(10));
                }

                // 检查是否超时
                auto now = std::chrono::steady_clock::now();
                int64_t elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - playback_start_time).count();
                if (target_duration_ms > 0 && elapsed >= target_duration_ms) {
                    should_stop = true;
                }
                continue;
            }

            // 限制队列大小 (生产者-消费者模型)
            // 如果队列满了，等待消费者(渲染线程)消费
            {
                std::unique_lock<std::mutex> lock(queue_mutex);
                if (frame_queue.size() >= MAX_QUEUE_SIZE) {
                     queue_cv.wait_for(lock, std::chrono::milliseconds(100), [this] { return frame_queue.size() < MAX_QUEUE_SIZE || should_stop; });
                     if (should_stop) break;
                }
            }
            if (should_stop) break; // 双重检查

            // 读取一个数据包 (Packet)
            int ret = av_read_frame(format_ctx, packet);
            if (ret < 0) {
                if (ret == AVERROR_EOF) {
                    std::cout << "视频播放结束" << std::endl;
                    should_stop = true; 
                }
                break;
            }

            if (packet->stream_index == video_stream_index) {
                // 发送 Packet 到解码器
                if (avcodec_send_packet(video_codec_ctx, packet) < 0) {
                    av_packet_unref(packet);
                    continue;
                }

                // 从解码器接收 Frame
                while (avcodec_receive_frame(video_codec_ctx, frame) == 0) {
                    // 格式转换 (SwScale)
                    int scale_ret = sws_scale(sws_ctx,
                        frame->data, frame->linesize, 0, frame->height,
                        yuv_frame->data, yuv_frame->linesize);

                    if (scale_ret <= 0) {
                        std::cerr << "sws_scale 转换失败或高度为0: " << scale_ret 
                                  << ", frame->format: " << frame->format << std::endl;
                        continue;
                    }

                    // 创建自定义 Frame 对象 (深拷贝数据)
                    auto video_frame = std::make_unique<Frame>();
                    video_frame->width = target_width;
                    video_frame->height = target_height;
                    video_frame->pts = frame->pts;

                    // 计算各平面大小
                    int y_plane_size = target_width * target_height;
                    int uv_plane_size = y_plane_size / 4;
                    int total_size = y_plane_size + uv_plane_size * 2;

                    video_frame->data = std::make_unique<uint8_t[]>(total_size);
                    uint8_t* dst = video_frame->data.get();

                    // 复制YUV数据到连续内存块 (便于 SDL 更新)
                    // Y Plane
                    for (int y = 0; y < target_height; y++) {
                        memcpy(dst, yuv_frame->data[0] + y * yuv_frame->linesize[0], target_width);
                        dst += target_width;
                    }
                    // U Plane
                    for (int y = 0; y < target_height / 2; y++) {
                        memcpy(dst, yuv_frame->data[1] + y * yuv_frame->linesize[1], target_width / 2);
                        dst += target_width / 2;
                    }
                    // V Plane
                    for (int y = 0; y < target_height / 2; y++) {
                        memcpy(dst, yuv_frame->data[2] + y * yuv_frame->linesize[2], target_width / 2);
                        dst += target_width / 2;
                    }

                    // 入队
                    {
                        std::unique_lock<std::mutex> lock(queue_mutex);
                        queue_cv.wait(lock, [this] { return frame_queue.size() < MAX_QUEUE_SIZE || should_stop; });
                        if (should_stop) break;
                        
                        frame_queue.push(std::move(video_frame));
                    }
                    queue_cv.notify_one(); // 通知渲染线程

                    frame_count++;
                    
                    // 简单帧率控制 (防止解码过快填满内存)
                    if (!is_image && frame_rate > 0 && frame_queue.size() > MAX_QUEUE_SIZE / 2) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(1));
                    }
                }
            }
            av_packet_unref(packet);
        }

        // 释放资源
        av_frame_free(&yuv_frame);
        av_frame_free(&frame);
        av_packet_free(&packet);
        std::cout << "解码线程退出" << std::endl;
    }

    void SetWindowTitle(const std::string& title);

    // 主线程更新函数 (替代原渲染线程)
    void Update() {
        if (window_open) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_QUIT) {
                    std::cout << "[VideoPlayer] Update: 收到 SDL_QUIT 事件 (用户点击关闭)" << std::endl;
                    should_stop = true;
                    queue_cv.notify_all(); 
                    is_playing = false;
                    window_open = false;
                    std::cout << "[VideoPlayer] Update: 已设置停止标志" << std::endl;
                } else if (event.type == SDL_KEYDOWN) {
                    if (event.key.keysym.sym == SDLK_ESCAPE) {
                        std::cout << "[VideoPlayer] Update: 收到 ESC 按键" << std::endl;
                        should_stop = true;
                        queue_cv.notify_all(); 
                        is_playing = false;
                        window_open = false;
                        std::cout << "[VideoPlayer] Update: 已设置停止标志" << std::endl;
                    }
                }
            }
        }


        if (!should_stop && window_open) {
            // 更新窗口标题显示进度
            if (is_playing && window) {
                auto now = std::chrono::steady_clock::now();
                int64_t elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - playback_start_time).count();
                int64_t total_ms = (target_duration_ms > 0) ? target_duration_ms : duration_ms;
                
                // 每 500ms 更新一次标题
                static auto last_title_update = now;
                if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_title_update).count() > 500) {
                    std::string progress_str;
                    if (total_ms > 0) {
                        int progress = (int)(elapsed_ms * 100 / total_ms);
                        progress = std::min(100, std::max(0, progress));
                        progress_str = " [" + std::to_string(progress) + "%]";
                    }
                    
                    std::string title = current_title + progress_str;
                    SDL_SetWindowTitle(window, title.c_str());
                    last_title_update = now;
                }
            }

            if (!is_paused) {
                // 帧率控制
                auto now = std::chrono::steady_clock::now();
                double elapsed = std::chrono::duration<double, std::milli>(now - last_render_time).count();
                double target_delay = (frame_rate > 0) ? (1000.0 / frame_rate) : 40.0;

                if (elapsed < target_delay) {
                    return;
                }
                last_render_time = now;

                std::unique_ptr<Frame> frame;
                {
                    std::unique_lock<std::mutex> lock(queue_mutex);
                    if (!frame_queue.empty()) {
                        frame = std::move(frame_queue.front());
                        frame_queue.pop();
                        queue_cv.notify_one(); // 通知解码线程可以继续生产
                    }
                }

                if (frame && renderer && texture) {
                    int y_size = frame->width * frame->height;
                    int uv_size = y_size / 4;

                    // IYUV 顺序: Y, U, V
                    // 参数顺序: texture, rect, Yplane, Ypitch, Uplane, Upitch, Vplane, Vpitch
                    // Frame data layout: [Y...][U...][V...]
                    SDL_UpdateYUVTexture(texture, nullptr,
                        frame->data.get(), frame->width,                           // Y
                        frame->data.get() + y_size, frame->width / 2,              // U
                        frame->data.get() + y_size + uv_size, frame->width / 2);   // V

                    SDL_RenderClear(renderer);
                    SDL_RenderCopy(renderer, texture, nullptr, nullptr);
                    SDL_RenderPresent(renderer);
                    
                    // 回调通知
                    if (frame_callback) {
                        frame_callback(frame->data.get(), frame->width, frame->height, frame->width);
                    }
                }
            }
        } else if (should_stop && is_playing) {
            // 如果已经被标记停止，确保状态同步
            is_playing = false;
            // 不要自动关闭窗口，保持窗口打开以便播放下一个视频
            // window_open = false; 
        }
    }
};

VideoPlayer::VideoPlayer() : pImpl(std::make_unique<Impl>()) {
    av_log_set_level(AV_LOG_ERROR);
}

VideoPlayer::~VideoPlayer() = default;

void VideoPlayer::CreateWindow(const std::string& title, int width, int height) {
    pImpl->width = width;
    pImpl->height = height;
    pImpl->CreateSDLWindow(title);
}

void VideoPlayer::CloseWindow() {
    pImpl->should_stop = true;
    pImpl->CleanupSDL();
}

bool VideoPlayer::Load(const std::string& filepath, int64_t duration_ms) {
    pImpl->CleanupDecoder(); // 只清理解码器资源，保留SDL窗口
    pImpl->should_stop = false;
    pImpl->target_duration_ms = duration_ms;
    pImpl->playback_start_time = std::chrono::steady_clock::now();

    std::cout << "加载媒体: " << filepath << std::endl;

    if (avformat_open_input(&pImpl->format_ctx, filepath.c_str(), nullptr, nullptr) < 0) {
        std::cerr << "无法打开文件: " << filepath << std::endl;
        return false;
    }

    if (avformat_find_stream_info(pImpl->format_ctx, nullptr) < 0) {
        std::cerr << "无法获取流信息" << std::endl;
        return false;
    }

    pImpl->video_stream_index = -1;
    for (unsigned int i = 0; i < pImpl->format_ctx->nb_streams; i++) {
        if (pImpl->format_ctx->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            pImpl->video_stream_index = i;
            pImpl->video_stream = pImpl->format_ctx->streams[i];
            break;
        }
    }

    if (pImpl->video_stream_index == -1) {
        std::cerr << "未找到视频流" << std::endl;
        return false;
    }

    AVCodecParameters* codecpar = pImpl->video_stream->codecpar;
    const AVCodec* codec = avcodec_find_decoder(codecpar->codec_id);
    if (!codec) {
        std::cerr << "不支持的解码器: " << codecpar->codec_id << std::endl;
        return false;
    }

    pImpl->video_codec_ctx = avcodec_alloc_context3(codec);
    avcodec_parameters_to_context(pImpl->video_codec_ctx, codecpar);

    if (avcodec_open2(pImpl->video_codec_ctx, codec, nullptr) < 0) {
        std::cerr << "无法打开解码器" << std::endl;
        return false;
    }

    std::cout << "解码器像素格式: " << av_get_pix_fmt_name(pImpl->video_codec_ctx->pix_fmt) 
              << " (" << pImpl->video_codec_ctx->pix_fmt << ")" << std::endl;

    pImpl->width = pImpl->video_codec_ctx->width;
    pImpl->height = pImpl->video_codec_ctx->height;
    pImpl->time_base = pImpl->video_stream->time_base;

    if (pImpl->video_stream->avg_frame_rate.den != 0) {
        pImpl->frame_rate = av_q2d(pImpl->video_stream->avg_frame_rate);
    }

    if (pImpl->format_ctx->duration != AV_NOPTS_VALUE) {
        pImpl->duration_ms = pImpl->format_ctx->duration * 1000 / AV_TIME_BASE;
    }

    // 判断是否为图片 (单帧且时长极短)
    if (pImpl->format_ctx->nb_streams == 1 && pImpl->video_stream->nb_frames == 1) {
        pImpl->is_image = true;
        std::cout << "检测到图片格式" << std::endl;
    } else {
        // 通过扩展名辅助判断
        size_t dot = filepath.find_last_of(".");
        if (dot != std::string::npos) {
            std::string ext = filepath.substr(dot + 1);
            if (ext == "jpg" || ext == "jpeg" || ext == "png" || ext == "bmp") {
                pImpl->is_image = true;
                std::cout << "检测到图片格式 (扩展名)" << std::endl;
            }
        }
    }

    std::cout << "媒体加载成功: " << pImpl->width << "x" << pImpl->height 
              << ", " << pImpl->frame_rate << " fps, " 
              << (pImpl->duration_ms / 1000.0) << "s" << std::endl;

    return true;
}

bool VideoPlayer::Play() {
    if (!pImpl->video_codec_ctx) {
        std::cerr << "请先加载视频" << std::endl;
        return false;
    }

    if (pImpl->is_playing) {
        std::cout << "视频已在播放中" << std::endl;
        return true;
    }

    pImpl->CreateSDLWindow("Edge Player");

    if (!pImpl->window) {
        std::cerr << "无法创建播放窗口" << std::endl;
        return false;
    }

    pImpl->is_playing = true;
    pImpl->is_paused = false;
    pImpl->should_stop = false;

    pImpl->last_render_time = std::chrono::steady_clock::now();
    pImpl->decode_thread = std::make_unique<std::thread>([this]() {
        pImpl->DecodeThreadFunc();
    });

    // 注意：渲染逻辑现在通过 Update() 在主线程调用
    return true;
}

void VideoPlayer::Update() {
    pImpl->Update();
}

bool VideoPlayer::Pause() {
    if (!pImpl->is_playing) return false;
    pImpl->is_paused = !pImpl->is_paused;
    return true;
}

bool VideoPlayer::Stop() {
    pImpl->should_stop = true;
    return true;
}

void VideoPlayer::Seek(int64_t timestamp_ms) {
    // TODO: 实现Seek
}

bool VideoPlayer::IsPlaying() const { return pImpl->is_playing; }
bool VideoPlayer::IsPaused() const { return pImpl->is_paused; }
bool VideoPlayer::IsWindowOpen() const { return pImpl->window_open; }
int64_t VideoPlayer::GetDuration() const { return pImpl->duration_ms; }
int64_t VideoPlayer::GetCurrentPosition() const { return 0; } // TODO
int VideoPlayer::GetWidth() const { return pImpl->width; }
int VideoPlayer::GetHeight() const { return pImpl->height; }
double VideoPlayer::GetFrameRate() const { return pImpl->frame_rate; }

void VideoPlayer::SetWindowTitle(const std::string& title) {
    pImpl->SetTitle(title);
}

void VideoPlayer::SetFrameCallback(FrameCallback callback) {
    pImpl->frame_callback = callback;
}
