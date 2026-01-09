# Contributing Guide (Cloud Backend)

本项目的 `cloud/` 目录为 **电梯广告投放系统的云端服务**，  
基于 **FastAPI**，所有云端相关功能统一在该服务中实现。

本文件用于约定 **云端模块的协作方式**，以减少冲突、提升集成效率。

---

## 一、基本原则

- `cloud/` 是 **一个独立的后端服务**
- **不为个人或子任务单独新建 cloud 目录**
- 在统一结构下 **按模块拆文件，不拆工程**

> 简单理解：  
> **共用工程结构，各写各的模块文件**

---

## 二、目录协作约定

```text
cloud/app/
├─ api/v1/endpoints/   # HTTP API 层（按功能拆文件）
├─ services/           # 业务逻辑层
├─ models/             # ORM 模型（表结构）
├─ schemas/            # 请求 / 响应数据结构
├─ tasks/              # 异步任务（Celery）
└─ main.py             # FastAPI 入口
