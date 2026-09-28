# Quick Start Guide - Chennai Fresher Jobs Scraper

Get started in 3 minutes! 🚀

## Step 1: Install (1 minute)

Open PowerShell in this folder and run:

```powershell
pip install -r requirements.txt
```

Wait for all packages to install. You'll need Chrome browser installed.

## Step 2: Run the Scraper (2-5 minutes)

### For One-Time Scraping:
```powershell
python enhanced_scraper.py
```

### For Real-Time Monitoring:
```powershell
python enhanced_scraper.py --realtime
```

The scraper will:
- ✅ Visit 10+ job websites
- ✅ Find Chennai fresher jobs
- ✅ Save results to database
- ✅ Show you a summary

## Step 3: View Results

Double-click `dashboard.html` to open in your browser.

You'll see:
- All fresher jobs in Chennai
- Company names and positions
- Direct apply links
- Search and filter options

## That's It! 🎉

The scraper found jobs from:
- Naukri
- Indeed
- Freshersworld
- Monster/Foundit
- TimesJobs
- Shine
- Internshala
- LinkedIn
- PlacementIndia
- And more!

## Next Steps

### Run Automatically Every Day

**Windows Task Scheduler:**
1. Search "Task Scheduler" in Start menu
2. Create Basic Task
3. Set to run daily at 9 AM
4. Program: `python.exe`
5. Arguments: `enhanced_scraper.py`
6. Start in: (this folder path)

### Customize Settings

Edit `config.json` to:
- Enable/disable job sources
- Change scraping interval
- Add more keywords
- Adjust filters

### Monitor Logs

Check `scraper.log` to see:
- What's being scraped
- New jobs found
- Any errors
- Statistics

## Troubleshooting

**"pip is not recognized"**
```powershell
python -m pip install -r requirements.txt
```

**"Chrome not found"**
- Install Chrome browser
- Or disable Selenium sources in config.json

**"No jobs found"**
- Sites may have changed - normal for first run
- Check scraper.log for details
- Try running again later

## Tips

1. **First run takes longer** (5-10 min) - downloads ChromeDriver
2. **Some sites may not work** - due to anti-scraping measures
3. **Be patient** - scraping 10+ sites takes time
4. **Run regularly** - to catch new postings
5. **Check dashboard often** - new jobs appear fast!

## Commands Cheat Sheet

```powershell
# Run once
python enhanced_scraper.py

# Run in real-time (every 30 min)
python enhanced_scraper.py --realtime

# Run every 15 minutes
python enhanced_scraper.py --realtime --interval 15

# View logs in real-time
Get-Content scraper.log -Wait -Tail 20

# Check if it's working
Get-Content scraper.log
```

## What You'll Find

The scraper looks for jobs with keywords like:
- Fresher
- Entry Level
- Graduate Trainee
- 0-1 years experience
- Campus Hire
- Trainee
- Junior roles
- Recent Graduate

All filtered for Chennai location! 🌆

## Need Help?

1. Read the full README.md
2. Check scraper.log for errors
3. Verify Chrome is installed
4. Test with one source first (edit config.json)

---

**Now start applying and land your dream job! 💼✨**
