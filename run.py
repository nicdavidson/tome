#!/usr/bin/env python3
import uvicorn
from config import Config
from db import init_db

if __name__ == "__main__":
    init_db()
    uvicorn.run("app:app", host=Config.HOST, port=Config.PORT, reload=False)
