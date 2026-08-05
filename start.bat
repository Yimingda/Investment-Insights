@echo off
rem 本地一键启动投资面板（浏览器自动打开 http://localhost:8501）
rem 局域网访问：改为  python -m streamlit run app.py --server.address 0.0.0.0
cd /d %~dp0
python -m streamlit run app.py
pause
