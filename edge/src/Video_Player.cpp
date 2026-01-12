// VideoPlayer.cpp
#include "./head file/Video_Player.h"
#include <iostream>
#include <thread>
#include <atomic>
#include <chrono>
#include <queue>
#include <mutex>
#include <condition_variable>

// PIMPL模式
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
    AVRational time_base;

    // 播放时间控制
    std::chrono::steady_clock::time_point start_time;
    int64_t pause_time_accumulated = 0;
    int64_t pause_start_time = 0;

    // 线程
    std::unique_ptr<std::thread> decode_thread;
    std::unique_ptr<std::thread> render_thread;

    // 回调函数
    VideoPlayer::FrameCallback frame_callback;

    ~Impl() {
        Cleanup();
    }

    void Cleanup() {
        should_stop = true;

        // 唤醒等待的线程
        queue_cv.notify_all();

        // 等待线程结束
        if (decode_thread && decode_thread->joinable()) {
            decode_thread->join();
        }
        if (render_thread && render_thread->joinable()) {
            render_thread->join();
        }

        // 清理SDL
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

        // 清理FFmpeg
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
        std::lock_guard<std::mutex> lock(queue_mutex);
        while (!frame_queue.empty()) {
            frame_queue.pop();
        }
    }

    void CreateSDLWindow(const std::string& title) {
        if (window) return;

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

        // 创建纹理（YUV420P格式）
        texture = SDL_CreateTexture(renderer,
            SDL_PIXELFORMAT_YV12,  // YUV420P格式
            SDL_TEXTUREACCESS_STREAMING,
            width, height);

        if (!texture) {
            std::cerr << "创建SDL纹理失败: " << SDL_GetError() << std::endl;
        }

        window_open = true;
        std::cout << "SDL窗口创建成功: " << width << "x" << height << std::endl;
    }

    // 解码线程函数
    void DecodeThreadFunc() {
        AVPacket* packet = av_packet_alloc();
        AVFrame* frame = av_frame_alloc();

        std::cout << "解码线程启动" << std::endl;
        std::cout << "源格式: " << av_get_pix_fmt_name(video_codec_ctx->pix_fmt)
            << " " << video_codec_ctx->width << "x" << video_codec_ctx->height << std::endl;

        // 关键：确保宽度和高度是偶数（YUV420P要求）
        int target_width = (video_codec_ctx->width + 1) & ~1;  // 对齐到偶数
        int target_height = (video_codec_ctx->height + 1) & ~1;

        std::cout << "目标分辨率: " << target_width << "x" << target_height << std::endl;

        // 创建SWS上下文 - 使用正确的参数
        sws_ctx = sws_getContext(
            video_codec_ctx->width, video_codec_ctx->height, video_codec_ctx->pix_fmt,
            target_width, target_height, AV_PIX_FMT_YUV420P,  // 目标格式固定为YUV420P
            SWS_BICUBIC,  // 使用更好的缩放算法
            nullptr, nullptr, nullptr);

        if (!sws_ctx) {
            std::cerr << "无法创建SWS上下文" << std::endl;
            return;
        }

        // 创建目标帧
        AVFrame* yuv_frame = av_frame_alloc();
        yuv_frame->format = AV_PIX_FMT_YUV420P;
        yuv_frame->width = target_width;
        yuv_frame->height = target_height;

        // 关键：分配对齐的内存
        int align = 32;  // 32字节对齐，提高性能
        if (av_frame_get_buffer(yuv_frame, align) < 0) {
            std::cerr << "无法分配帧缓冲区" << std::endl;
            av_frame_free(&yuv_frame);
            return;
        }

        // 计算预期的数据大小
        int y_size = target_width * target_height;
        int uv_size = y_size / 4;  // YUV420P: UV分量是Y的1/4
        std::cout << "预期数据大小: Y=" << y_size << " U/V=" << uv_size << std::endl;

        // 帧计数器
        int frame_count = 0;
        bool first_frame = true;

        while (!should_stop) {
            if (is_paused) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }

            // 读取数据包
            int ret = av_read_frame(format_ctx, packet);
            if (ret < 0) {
                // 文件结束或错误
                if (ret == AVERROR_EOF) {
                    std::cout << "视频播放结束" << std::endl;
                    // 可以在这里添加循环播放逻辑
                    av_seek_frame(format_ctx, video_stream_index, 0, AVSEEK_FLAG_BACKWARD);
                    continue;
                }
                break;
            }

            // 只处理视频流
            if (packet->stream_index == video_stream_index) {
                // 发送到解码器
                if (avcodec_send_packet(video_codec_ctx, packet) < 0) {
                    av_packet_unref(packet);
                    continue;
                }

                // 接收解码后的帧
                while (avcodec_receive_frame(video_codec_ctx, frame) == 0) {
                    // 打印第一帧详细信息
                    if (first_frame) {
                        first_frame = false;
                        std::cout << "\n第一帧详细信息:" << std::endl;
                        std::cout << "  原始尺寸: " << frame->width << "x" << frame->height << std::endl;
                        std::cout << "  原始格式: " << av_get_pix_fmt_name((AVPixelFormat)frame->format) << std::endl;
                        std::cout << "  行大小: linesize[0]=" << frame->linesize[0]
                            << " linesize[1]=" << frame->linesize[1]
                            << " linesize[2]=" << frame->linesize[2] << std::endl;
                    }

                    // 转换帧格式
                    sws_scale(sws_ctx,
                        frame->data, frame->linesize, 0, frame->height,
                        yuv_frame->data, yuv_frame->linesize);

                    // 检查数据有效性
                    if (!yuv_frame->data[0] || !yuv_frame->data[1] || !yuv_frame->data[2]) {
                        std::cerr << "转换后的帧数据为空" << std::endl;
                        continue;
                    }

                    // 调试信息
                    if (frame_count == 0) {
                        std::cout << "\n转换后帧信息:" << std::endl;
                        std::cout << "  Y平面行大小: " << yuv_frame->linesize[0] << std::endl;
                        std::cout << "  U平面行大小: " << yuv_frame->linesize[1] << std::endl;
                        std::cout << "  V平面行大小: " << yuv_frame->linesize[2] << std::endl;
                    }

                    // 创建帧数据
                    auto video_frame = std::make_unique<Frame>();
                    video_frame->width = target_width;
                    video_frame->height = target_height;
                    video_frame->pts = frame->pts;

                    // 计算每个平面的大小
                    int y_plane_size = target_width * target_height;
                    int uv_plane_size = y_plane_size / 4;
                    int total_size = y_plane_size + uv_plane_size * 2;

                    video_frame->data = std::make_unique<uint8_t[]>(total_size);
                    uint8_t* dst = video_frame->data.get();

                    // 关键：正确复制YUV数据
                    // 1. 复制Y平面（全尺寸）
                    for (int y = 0; y < target_height; y++) {
                        memcpy(dst, yuv_frame->data[0] + y * yuv_frame->linesize[0], target_width);
                        dst += target_width;
                    }

                    // 2. 复制U平面（半尺寸）
                    for (int y = 0; y < target_height / 2; y++) {
                        memcpy(dst, yuv_frame->data[1] + y * yuv_frame->linesize[1], target_width / 2);
                        dst += target_width / 2;
                    }

                    // 3. 复制V平面（半尺寸）
                    for (int y = 0; y < target_height / 2; y++) {
                        memcpy(dst, yuv_frame->data[2] + y * yuv_frame->linesize[2], target_width / 2);
                        dst += target_width / 2;
                    }

                    // 添加到队列
                    {
                        std::lock_guard<std::mutex> lock(queue_mutex);
                        if (frame_queue.size() < MAX_QUEUE_SIZE) {
                            frame_queue.push(std::move(video_frame));
                            queue_cv.notify_one();
                        }
                    }

                    // 回调（用于调试）
                    if (frame_callback) {
                        frame_callback(video_frame->data.get(), target_width, target_height, target_width);
                    }

                    frame_count++;
                    if (frame_count % 30 == 0) {
                        std::cout << "已解码 " << frame_count << " 帧" << std::endl;
                    }

                    // 简单的帧率控制
                    if (frame_rate > 0) {
                        std::this_thread::sleep_for(
                            std::chrono::milliseconds(static_cast<int>(1000 / frame_rate))
                        );
                    }
                }
            }

            av_packet_unref(packet);
        }

        std::cout << "解码线程结束，共解码 " << frame_count << " 帧" << std::endl;

        // 清理资源
        av_frame_free(&yuv_frame);
        av_frame_free(&frame);
        av_packet_free(&packet);
    }

    // 渲染线程函数
    void RenderThreadFunc() {
        while (!should_stop && window_open) {
            // 处理SDL事件
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_QUIT) {
                    should_stop = true;
                    break;
                }
                else if (event.type == SDL_KEYDOWN) {
                    switch (event.key.keysym.sym) {
                    case SDLK_SPACE:
                        is_paused = !is_paused;
                        std::cout << (is_paused ? "已暂停" : "已恢复") << std::endl;
                        break;
                    case SDLK_ESCAPE:
                        should_stop = true;
                        break;
                    }
                }
                else if (event.type == SDL_WINDOWEVENT) {
                    if (event.window.event == SDL_WINDOWEVENT_CLOSE) {
                        should_stop = true;
                    }
                }
            }

            // 渲染帧
            if (!is_paused) {
                std::unique_ptr<Frame> frame;
                {
                    std::unique_lock<std::mutex> lock(queue_mutex);
                    if (queue_cv.wait_for(lock, std::chrono::milliseconds(100),
                        [this] { return !frame_queue.empty() || should_stop; })) {

                        if (!frame_queue.empty()) {
                            frame = std::move(frame_queue.front());
                            frame_queue.pop();
                        }
                    }
                }

                if (frame && renderer && texture) {
                    // 更新纹理
                    int y_size = frame->width * frame->height;
                    int uv_size = y_size / 4;

                    SDL_UpdateYUVTexture(texture, nullptr,
                        frame->data.get(), frame->width,                     // Y
                        frame->data.get() + y_size, frame->width / 2,       // U
                        frame->data.get() + y_size + uv_size, frame->width / 2); // V

                    // 渲染
                    SDL_RenderClear(renderer);
                    SDL_RenderCopy(renderer, texture, nullptr, nullptr);
                    SDL_RenderPresent(renderer);
                }
            }

            // 控制帧率
            std::this_thread::sleep_for(std::chrono::milliseconds(16)); // ~60fps
        }

        window_open = false;
    }
};

// VideoPlayer成员函数实现
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
    pImpl->window_open = false;
}

bool VideoPlayer::Load(const std::string& filepath) {
    pImpl->Cleanup();
    pImpl->should_stop = false;

    std::cout << "加载视频: " << filepath << std::endl;

    // 1. 打开文件
    if (avformat_open_input(&pImpl->format_ctx, filepath.c_str(), nullptr, nullptr) < 0) {
        std::cerr << "无法打开文件: " << filepath << std::endl;
        return false;
    }

    // 2. 获取流信息
    if (avformat_find_stream_info(pImpl->format_ctx, nullptr) < 0) {
        std::cerr << "无法获取流信息" << std::endl;
        return false;
    }

    // 3. 查找视频流
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

    // 4. 获取解码器
    AVCodecParameters* codecpar = pImpl->video_stream->codecpar;
    const AVCodec* codec = avcodec_find_decoder(codecpar->codec_id);
    if (!codec) {
        std::cerr << "不支持的解码器: " << codecpar->codec_id << std::endl;
        return false;
    }

    // 5. 创建解码器上下文
    pImpl->video_codec_ctx = avcodec_alloc_context3(codec);
    avcodec_parameters_to_context(pImpl->video_codec_ctx, codecpar);

    if (avcodec_open2(pImpl->video_codec_ctx, codec, nullptr) < 0) {
        std::cerr << "无法打开解码器" << std::endl;
        return false;
    }

    // 6. 获取视频信息
    pImpl->width = pImpl->video_codec_ctx->width;
    pImpl->height = pImpl->video_codec_ctx->height;
    pImpl->time_base = pImpl->video_stream->time_base;

    if (pImpl->video_stream->avg_frame_rate.den != 0) {
        pImpl->frame_rate = av_q2d(pImpl->video_stream->avg_frame_rate);
    }

    if (pImpl->format_ctx->duration != AV_NOPTS_VALUE) {
        pImpl->duration_ms = pImpl->format_ctx->duration * 1000 / AV_TIME_BASE;
    }

    std::cout << "视频信息:" << std::endl;
    std::cout << "  分辨率: " << pImpl->width << "x" << pImpl->height << std::endl;
    std::cout << "  帧率: " << pImpl->frame_rate << " fps" << std::endl;
    std::cout << "  时长: " << (pImpl->duration_ms / 1000.0) << " 秒" << std::endl;
    std::cout << "  编码器: " << codec->name << std::endl;

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

    // 创建窗口
    pImpl->CreateSDLWindow("Video Player");

    if (!pImpl->window) {
        std::cerr << "无法创建播放窗口" << std::endl;
        return false;
    }

    pImpl->is_playing = true;
    pImpl->is_paused = false;
    pImpl->should_stop = false;

    // 启动解码线程
    pImpl->decode_thread = std::make_unique<std::thread>([this]() {
        pImpl->DecodeThreadFunc();
        });

    // 启动渲染线程
    pImpl->render_thread = std::make_unique<std::thread>([this]() {
        pImpl->RenderThreadFunc();
        });

    std::cout << "开始播放视频..." << std::endl;
    return true;
}

bool VideoPlayer::Pause() {
    if (!pImpl->is_playing) return false;

    pImpl->is_paused = !pImpl->is_paused;
    std::cout << (pImpl->is_paused ? "已暂停" : "已恢复") << std::endl;
    return true;
}

bool VideoPlayer::Stop() {
    pImpl->should_stop = true;
    pImpl->is_playing = false;
    return true;
}

void VideoPlayer::SetFrameCallback(FrameCallback callback) {
    pImpl->frame_callback = callback;
}

// 获取信息的方法
int VideoPlayer::GetWidth() const { return pImpl->width; }
int VideoPlayer::GetHeight() const { return pImpl->height; }
double VideoPlayer::GetFrameRate() const { return pImpl->frame_rate; }
int64_t VideoPlayer::GetDuration() const { return pImpl->duration_ms; }
bool VideoPlayer::IsPlaying() const { return pImpl->is_playing; }
bool VideoPlayer::IsPaused() const { return pImpl->is_paused; }
bool VideoPlayer::IsWindowOpen() const { return pImpl->window_open; }

int64_t VideoPlayer::GetCurrentPosition() const {
    return 0; // TODO: 实现精确的时间计算
}

void VideoPlayer::Seek(int64_t timestamp_ms) {
    // TODO: 实现跳转
    std::cout << "跳转到: " << timestamp_ms << "ms" << std::endl;
}