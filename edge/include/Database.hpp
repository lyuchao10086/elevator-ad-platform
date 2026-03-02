#ifndef DATABASE_HPP
#define DATABASE_HPP

#include <sqlite3.h>
#include <string>
#include <stdexcept>
#include <vector>
#include <map>

/**
 * @brief 数据库管理类
 * 
 * 负责 SQLite 数据库的连接管理（打开/关闭）以及执行 SQL 语句。
 * 采用 RAII (Resource Acquisition Is Initialization) 机制，
 * 在构造函数中打开数据库，在析构函数中自动关闭数据库。
 */
class Database {
public:
    /**
     * @brief 构造函数：创建 Database 对象并打开数据库连接
     * 
     * @param dbPath SQLite 数据库文件的路径（例如 "schedule.db"）
     * @throws std::runtime_error 如果无法打开数据库，将抛出运行时异常
     */
    Database(const std::string& dbPath);

    /**
     * @brief 析构函数：销毁 Database 对象并关闭数据库连接
     * 
     * 确保在对象生命周期结束时释放数据库资源。
     */
    ~Database();

    // 禁止拷贝构造和赋值操作，以确保数据库连接的所有权唯一，避免重复关闭连接等问题
    Database(const Database&) = delete;
    Database& operator=(const Database&) = delete;

    /**
     * @brief 执行无返回结果的 SQL 语句
     * 
     * 适用于 CREATE TABLE, INSERT, UPDATE, DELETE 等操作。
     * 
     * @param sql 要执行的 SQL 查询字符串
     * @throws std::runtime_error 如果 SQL 执行失败，将抛出运行时异常
     */
    void execute(const std::string& sql);

    std::vector<std::map<std::string, std::string>> query(const std::string& sql) const;

private:
    sqlite3* db_;         // SQLite 数据库连接句柄指针
    std::string dbPath_;  // 数据库文件路径
};

#endif // DATABASE_HPP
