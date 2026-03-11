#include "Database.hpp"
#include <iostream>

Database::Database(const std::string& dbPath) : db_(nullptr) {
    int rc = sqlite3_open(dbPath.c_str(), &db_);
    
    if (rc) {
        std::string errorMsg = "无法打开数据库: " + std::string(sqlite3_errmsg(db_));
        sqlite3_close(db_); 
        throw std::runtime_error(errorMsg);
    }
    
    std::cout << "成功打开数据库: " << dbPath << std::endl;
}

Database::~Database() {
    if (db_) {
        sqlite3_close(db_);
        std::cout << "已关闭数据库连接" << std::endl;
    }
}

bool Database::execute(const std::string& sql) {
    std::lock_guard<std::mutex> lock(mutex_);
    char* zErrMsg = 0;
    
    int rc = sqlite3_exec(db_, sql.c_str(), nullptr, 0, &zErrMsg);
    
    if (rc != SQLITE_OK) {
        std::string errorMsg = "SQL 执行错误: " + std::string(zErrMsg);
        sqlite3_free(zErrMsg);
        throw std::runtime_error(errorMsg);
    }
    
    // std::cout << "SQL 执行成功" << std::endl;
    return true;
}

// ... (queryCallback 保持不变)

std::vector<std::map<std::string, std::string>> Database::query(const std::string& sql) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::map<std::string, std::string>> results;
    char* zErrMsg = 0;
    
    // lambda callback
    auto callback = [](void* data, int argc, char** argv, char** azColName) -> int {
        auto* results = static_cast<std::vector<std::map<std::string, std::string>>*>(data);
        std::map<std::string, std::string> row;
        for (int i = 0; i < argc; i++) {
            row[azColName[i] ? azColName[i] : ""] = argv[i] ? argv[i] : "";
        }
        results->push_back(row);
        return 0;
    };

    int rc = sqlite3_exec(db_, sql.c_str(), callback, &results, &zErrMsg);
    
    if (rc != SQLITE_OK) {
        std::string errorMsg = "SQL 查询错误: " + (zErrMsg ? std::string(zErrMsg) : "Unknown error");
        sqlite3_free(zErrMsg);
        // throw std::runtime_error(errorMsg); // 最好不要直接 throw，或者在外面捕获
        std::cerr << errorMsg << std::endl;
        return {};
    }
    
    // std::cout << "SQL 查询成功: " << results.size() << " 行" << std::endl;
    return results;
}

bool Database::beginTransaction() {
    return execute("BEGIN TRANSACTION;");
}

bool Database::commit() {
    return execute("COMMIT;");
}

bool Database::rollback() {
    return execute("ROLLBACK;");
}
