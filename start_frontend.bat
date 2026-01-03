@echo off
cd frontend
if not exist node_modules (
    echo Installing dependencies...
    call npm install
)
echo Starting frontend development server...
call npm run dev
pause

