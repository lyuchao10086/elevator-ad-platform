# Schedule Manager

该模块负责解析 JSON 格式的排期策略文件，将其持久化存储到本地 SQLite 数据库中，并提供对象的增删改查（CRUD）接口供上层应用调用、根据优先级计算下一个待播放文件以及使用算法清理过期媒体文件

## 📂 项目结构

```
schedule/
├── include/                # 头文件
│   ├── models/             # 实体类定义 (Asset, Schedule, TimeSlot, Interrupt, PlayItem)
│   ├── nlohmann/           # JSON 库
│   ├── Database.hpp        # SQLite 封装类
│   └── ScheduleManager.hpp # 核心管理类 
├── src/                    # 源代码
│   ├── models/             # 实体类实现
│   ├── Database.cpp        # SQLite 操作实现
│   ├── ScheduleManager.cpp # 业务逻辑与 DB 交互实现
│   ├── test.cpp 						# 测试部分
│   └── main.cpp            # 程序入口与测试代码
├── resources/              # 资源文件 (测试用 JSON)
├── CMakeLists.txt          # CMake 构建脚本
├── README.md               # 项目文档
└── schedule.mdj            # 项目类图
```

## 💾 类设计

![image-20260210145439538](/Users/lyuchao/Library/Application Support/typora-user-images/image-20260210145439538.png)

系统使用 SQLite 存储数据，包含以下核心表：

**PlayItem**

- 存储播放时的信息

  ![image-20260210183014739](/Users/lyuchao/Library/Application Support/typora-user-images/image-20260210183014739.png)

**schedules**

* 存储全局排期策略（策略ID, 生效日期, 下发参数等）。

  ![image-20260210183047187](/Users/lyuchao/Library/Application Support/typora-user-images/image-20260210183047187.png)

**interrupts**

* 关联到策略，定义插播广告规则（触发条件, 优先级, 播放模式）。

* 外键关联: `schedules(policy_id)` (级联删除)。

  ![image-20260210183117923](/Users/lyuchao/Library/Application Support/typora-user-images/image-20260210183117923.png)

**time_slots**

* 关联到策略，定义分时段播放规则。

* 包含 `playlist` 字段，以 JSON 字符串形式存储该时间段的素材 ID 列表。

* 外键关联: `schedules(policy_id)` (级联删除)。

  ![image-20260210183141249](/Users/lyuchao/Library/Application Support/typora-user-images/image-20260210183141249.png)

**assets**

* 存储媒体文件信息（ID, 类型, 文件名, MD5, 时长等）。

  ![image-20260210183211038](/Users/lyuchao/Library/Application Support/typora-user-images/image-20260210183211038.png)

## 🚀 核心功能接口

##### JSON格式

```json
{
  "assets": [
    {
      "id": "AD_NIKE_01",
      "type": "video",
      "filename": "nike_2026_q1.mp4",
      "md5": "a1b2c3d4e5f6...",
      "duration": 300,
      "bytes": 20971520,
      "last_played_time": 0
    },
    {
      "id": "AD_COKE_CNY",
      "type": "video",
      "filename": "coke_cny_final.mp4",
      "md5": "f9e8d7c6b5...",
      "duration": 900,
      "bytes": 10485760,
      "last_played_time": 0
    },
    {
      "id": "AD_公益_01",
      "type": "image",
      "filename": "public_welfare.jpg",
      "md5": "f9e84d56b5...",
      "duration": 10,
      "bytes": 1048576,
      "last_played_time": 0
    },
    {
      "id": "AD_APP_PROMO",
      "type": "video",
      "filename": "ad_app_promo.mp4",
      "md5": "f9e84d56b5...",
      "duration": 600,
      "bytes": 10485760,
      "last_played_time": 0
    },
    {
      "id": "AD_LOGO_01",
      "type": "image",
      "filename": "ad_logo_01.jpg",
      "md5": "f9e84d56b5...",
      "duration": 10,
      "bytes": 2097152,
      "last_played_time": 0
    }
  ]
}
```

```json
{
  "policy_id": "POL_SH_20260112_V1",
  "effective_date": "2026-01-12",
  "download_base_url": "https://oss.cdn.com/ads/",
  "default_volume": 60,
  "download_retry_count": 3,
  "report_interval_sec": 60,
  "interrupts": {
    "trigger_type": "command",
    "ad_id": "AD_EMERGENCY_FIRE",
    "priority": 9,
    "play_mode": "loop_until_stop"
  },
  "time_slots": [
    {
      "slot_id": 1,
      "time_range": "08:00:00-10:00:00",
      "volume": 80,
      "priority": 7,
      "loop_mode": "sequence",
      "playlist": [
        "AD_NIKE_01",
        "AD_COKE_CNY"
      ]
    },
    {
      "slot_id": 2,
      "time_range": "17:00:00-19:00:00",
      "volume": 50,
      "priority": 7,
      "loop_mode": "sequence",
      "playlist": [
        "AD_NIKE_01",
        "AD_APP_PROMO"
      ]
    },
    {
      "slot_id": 3,
      "time_range": "00:00:00-23:59:59",
      "volume": 0,
      "priority": 2,
      "loop_mode": "random",
      "playlist": [
        "AD_公益_01",
        "AD_LOGO_01"
      ]
    }
  ]
}
```



##### 对象公有的接口，例：Object对象

```c++
//无参构造
Object();

//有参数构造
Object(ElemType1 param1, ElemType2 param2, ...);

//从Json对象拷贝构造
Object(const json& j);

//Getter和Setter
...

//序列化为Json对象
json toJson() const;

//序列化为字符串
string toString() const;

// nlohmann/json 序列化/反序列化辅助函数
void to_json(json& j, const Object& p);
void from_json(const json& j, Object& p);
```



##### 数据库接口(Database.hpp)

```C++
//执行无返回结果的 SQL 语句，用于建表、增、删、改操作
void execute(const string& sql);

//执行有返回结果的 SQL 语句，用于查询操作
vector<map<string, string>> query(const string& sql);
```



##### 管理模块接口(ScheduleManager.hpp)

```C++
//初始化数据库、建库、建表等操作
void initSchema();

//清除数据库中的所有内容
void clearAll();

//同步云端下发的Json播放清单，存入本地数据库
void syncSchedule(const string& jsonStr);

//参数为插播对象，若对象存在，则进行插播相关逻辑
bool triggerInterrupt(const Interrupt& interrupt);

//参数为插播对象，根据数据库中的内容以及插播对象，计算出下一个应该播放的媒体文件，并存入相应数据库
optional<Asset> getNextAsset(const optional<Interrupt>& interrupt);

//获取当前播放列表
vector<PlayItem> getPlayQueue() const;

//刷新播放列表
void refreshPlayQueue();

//使用LRU算法，清理占用超过限制的磁盘广告媒体文件
void cleanStorage(long long maxBytes);

//对广告资源的增删改查操作
void insertAsset(const Asset& asset);
optional<Asset> getAsset(const string& id);
void updateAsset(const Asset& asset);
void deleteAsset(const string& id);

//对播放清单以及相关联的实体的增删改查操作
void insertSchedule(const Schedule& schedule);
optional<Schedule> getSchedule(const string& policyId);
void updateSchedule(const Schedule& schedule);
void deleteSchedule(const string& policyId);
```

