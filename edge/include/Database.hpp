/**
 * @file Database.hpp
 * @brief SQLite 数据库操作封装类
 * @author Trae AI
 * @date 2026-03-05
 * 
 * 封装了 sqlite3 的 C API，提供面向对象的数据库操作接口。
 * 支持执行 SQL 语句、查询数据、事务处理等。
 */

#pragma once

#include <sqlite3.h>
#include <string>
#include <vector>
#include <map>
#include <stdexcept>
#include <mutex>

/**
 * @class Database
 * @brief 数据库管理类
 * 
 * 使用 RAII 管理数据库连接资源。
 * 提供简单的 execute 和 query 接口。
 */
class Database {
public:
    /**
     * @brief 构造函数，打开数据库连接
     * 
     * @param dbPath 数据库文件路径
     * @throws std::runtime_error 如果打开失败抛出异常
     */
    Database(const std::string& dbPath);

    /**
     * @brief 析构函数，关闭数据库连接
     */
    ~Database();

    /**
     * @brief 执行非查询 SQL 语句
     * 
     * 适用于 CREATE, INSERT, UPDATE, DELETE 等操作。
     * 
     * @param sql SQL 语句
     * @return true 执行成功
     * @throws std::runtime_error 如果执行出错抛出异常
     */
    bool execute(const std::string& sql);

    /**
     * @brief 执行查询 SQL 语句
     * 
     * 适用于 SELECT 操作。
     * 
     * @param sql SQL 查询语句
     * @return std::vector<std::map<std::string, std::string>> 
     *         查询结果集，每行是一个 map (列名 -> 值)
     * @throws std::runtime_error 如果查询出错抛出异常
     */
    std::vector<std::map<std::string, std::string>> query(const std::string& sql);

    /**
     * @brief 开启事务
     * @return true 成功
     */
    bool beginTransaction();

    /**
     * @brief 提交事务
     * @return true 成功
     */
    bool commit();

    /**
     * @brief 回滚事务
     * @return true 成功
     */
    bool rollback();

private:
    sqlite3* db_; ///< SQLite 数据库连接句柄
    std::mutex mutex_; ///< 数据库访问互斥锁
};
