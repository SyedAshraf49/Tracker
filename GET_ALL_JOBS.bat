@echo off
REM ============================================
REM GET ALL CHENNAI FRESHER JOBS
REM Ultra Scraper - Scrapes from 14+ websites
REM ============================================

echo.
echo ============================================
echo    CHENNAI FRESHER JOBS - ULTRA SCRAPER
echo ============================================
echo.
echo Getting jobs from ALL websites:
echo   - Freshersworld
echo   - LinkedIn
echo   - Naukri (Selenium)
echo   - Indeed (Selenium)
echo   - Monster
echo   - Internshala
echo   - TimesJobs
echo   - Shine
echo   - And more...
echo.
echo This will take 3-5 minutes...
echo ============================================
echo.

py ultra_scraper.py

echo.
echo ============================================
echo.
echo DONE! Now open dashboard.html to see jobs
echo.
echo Companies and direct links included!
echo ============================================
echo.
pause
