@echo off
REM Chennai Fresher Jobs Scraper - Real-Time Mode
REM Double-click this file to run continuous monitoring

echo ========================================
echo Chennai Fresher Jobs Scraper
echo REAL-TIME MODE
echo ========================================
echo.
echo Starting real-time job monitoring...
echo The scraper will run every 30 minutes automatically
echo.
echo Press Ctrl+C to stop
echo.
echo Logs are saved to scraper.log
echo ========================================
echo.

python enhanced_scraper.py --realtime

pause
