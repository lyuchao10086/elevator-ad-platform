#include "Database.hpp"
#include <iostream>

Database::Database(const std::string& dbPath) : dbPath_(dbPath), db_(nullptr) {
    // 尝试打开数据库连接
    // sqlite3_open 会打开已存在的数据库文件，如果不存在则会创建一个新的
    int rc = sqlite3_open(dbPath.c_str(), &db_);
    
    if (rc) {
        // 如果打开失败，获取错误信息
        std::string errorMsg = "无法打开数据库: " + std::string(sqlite3_errmsg(db_));
        
        // 即使打开失败，sqlite3_open 也可能分配了资源，需要调用 close 来释放
        sqlite3_close(db_); 
        
        // 抛出异常通知调用者初始化失败
        throw std::runtime_error(errorMsg);
    }
    
    std::cout << "成功打开数据库: " << dbPath_ << std::endl;
}

Database::~Database() {
    // 如果数据库连接句柄有效，则关闭连接
    if (db_) {
        sqlite3_close(db_);
        std::cout << "已关闭数据库连接: " << dbPath_ << std::endl;
    }
}

void Database::execute(const std::string& sql) {
    char* zErrMsg = 0;
    
    int rc = sqlite3_exec(db_, sql.c_str(), nullptr, 0, &zErrMsg);
    
    if (rc != SQLITE_OK) {
        std::string errorMsg = "SQL 执行错误: " + std::string(zErrMsg);
        
        sqlite3_free(zErrMsg);
        
        throw std::runtime_error(errorMsg);
    }
    
    std::cout << "SQL 执行成功" << std::endl;
}

static int queryCallback(void* data, int argc, char** argv, char** azColName) {
    auto* results = reinterpret_cast<std::vector<std::map<std::string, std::string>>*>(data);
    std::map<std::string, std::string> row;
    for (int i = 0; i < argc; ++i) {
        std::string key = azColName[i] ? azColName[i] : "";
        std::string value = argv[i] ? argv[i] : "";
        row[key] = value;
    }
    results->push_back(std::move(row));
    return 0;
}

std::vector<std::map<std::string, std::string>> Database::query(const std::string& sql) const {
    std::vector<std::map<std::string, std::string>> results;
    char* zErrMsg = 0;
    int rc = sqlite3_exec(db_, sql.c_str(), queryCallback, &results, &zErrMsg);
    if (rc != SQLITE_OK) {
        std::string errorMsg = "SQL 查询错误: " + std::string(zErrMsg);
        sqlite3_free(zErrMsg);
        throw std::runtime_error(errorMsg);
    }
    return results;
}
