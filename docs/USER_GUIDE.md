# FinStream User Guide

> **Paper Trading Platform with Real-Time Market Data**

Welcome to FinStream! This guide will help you get started with paper trading using virtual cash and real market prices.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard Overview](#dashboard-overview)
3. [Managing Your Portfolio](#managing-your-portfolio)
4. [Executing Trades](#executing-trades)
5. [Viewing Stock Details](#viewing-stock-details)
6. [Leaderboard](#leaderboard)
7. [Tips for Success](#tips-for-success)

---

## Getting Started

### Creating Your Account

1. Navigate to **http://localhost:3000/login**
2. Click the **"Register"** tab
3. Fill in your details:
   - **Email**: Your email address
   - **Username**: Choose a unique username (3-30 characters)
   - **Password**: At least 8 characters
   - **Full Name**: Optional
4. Click **"Register"**

You'll automatically receive **$10,000 in virtual cash** to start trading!

### Logging In

1. Go to **http://localhost:3000/login**
2. Enter your **email** and **password**
3. Click **"Login"**
4. You'll be redirected to the Market Overview dashboard

### Session Management

- Your login session lasts **30 minutes**
- If your session expires, you'll be redirected to login
- Click **"Logout"** in the navigation menu to end your session

---

## Dashboard Overview

### Market Overview (Home Page)

The main dashboard at **http://localhost:3000** displays:

| Element | Description |
|---------|-------------|
| **Stock Cards** | Real-time prices for major stocks (AAPL, GOOGL, MSFT, etc.) |
| **Price Indicators** | Green ↑ or Red ↓ arrows showing price movement |
| **Last Updated** | Timestamp of the latest price refresh |

**Features:**
- Prices refresh automatically every **5 seconds**
- Click any stock card to view detailed information
- Data is sourced from Yahoo Finance for real market prices

### Navigation Menu

| Menu Item | Description |
|-----------|-------------|
| **Dashboard** | Market overview with all stock prices |
| **Portfolio** | Your holdings, P&L, and trading interface |
| **Leaderboard** | Rankings of public portfolios |
| **Logout** | End your session |

---

## Managing Your Portfolio

### Accessing Your Portfolio

1. Click **"Portfolio"** in the navigation menu
2. Or navigate directly to **http://localhost:3000/portfolio**

### Portfolio Summary

Your portfolio page displays:

**Summary Cards:**
- **Cash Balance**: Available cash for new purchases
- **Holdings Value**: Current market value of all stocks
- **Total Value**: Cash + Holdings
- **Total P&L**: Overall profit/loss (with percentage)

**Holdings Table:**
| Column | Description |
|--------|-------------|
| Symbol | Stock ticker |
| Quantity | Number of shares owned |
| Avg Cost | Average purchase price per share |
| Current Price | Live market price |
| Market Value | Quantity × Current Price |
| P&L | Unrealized profit/loss |
| P&L % | Percentage gain/loss |

### Understanding P&L Colors

- 🟢 **Green**: Profit (stock is worth more than you paid)
- 🔴 **Red**: Loss (stock is worth less than you paid)
- ⚪ **Gray**: No change

---

## Executing Trades

### Buying Stocks

1. Go to your **Portfolio** page
2. Click the **"Buy Stock"** button
3. In the dialog:
   - Enter the **Stock Symbol** (e.g., AAPL, MSFT)
   - Enter the **Quantity** (number of shares)
4. Click **"Buy"**

**What happens:**
- The system fetches the **real-time price** from Yahoo Finance
- Total cost (Quantity × Price) is deducted from your cash
- The stock appears in your Holdings table
- A transaction record is created

**Validation:**
- You cannot buy more than you can afford
- The symbol must be valid and tradeable
- Quantity must be greater than 0

### Selling Stocks

1. Go to your **Portfolio** page
2. Find the stock you want to sell in your Holdings
3. Click the **"Sell"** button next to it
4. In the dialog:
   - Quantity is pre-filled with your total shares
   - Adjust the quantity if selling partial position
5. Click **"Sell"**

**What happens:**
- The system fetches the **real-time price** from Yahoo Finance
- Proceeds (Quantity × Price) are added to your cash
- Realized P&L is calculated and recorded
- Your holding is updated or removed

**Validation:**
- You cannot sell more shares than you own
- Quantity must be greater than 0

### Viewing Transaction History

At the bottom of the Portfolio page, you'll see your **Transaction History**:

| Column | Description |
|--------|-------------|
| Date | When the trade was executed |
| Type | BUY or SELL |
| Symbol | Stock ticker |
| Quantity | Number of shares |
| Price | Execution price |
| Total | Transaction amount |

---

## Viewing Stock Details

### Accessing Stock Details

1. From the **Dashboard**, click any stock card
2. Or navigate to **http://localhost:3000/symbol/AAPL** (replace AAPL with any symbol)

### Stock Detail Page

**Real-Time Quote Section:**
- **Current Price**: Live price with automatic refresh
- **Price Change**: Today's change in dollars and percentage
- **Open/High/Low/Close**: Daily trading range
- **Previous Close**: Yesterday's closing price
- **Volume**: Number of shares traded today

**1-Minute Candles Table:**
Shows aggregated OHLCV data:
- Open, High, Low, Close prices
- Volume per minute
- Trade count (if available)

**Recent Trades Table:**
Shows individual trade executions:
- Timestamp
- Price
- Quantity
- Side (BUY/SELL)

---

## Leaderboard

### Accessing the Leaderboard

1. Click **"Leaderboard"** in the navigation
2. Or navigate to **http://localhost:3000/leaderboard**

### Leaderboard Rankings

The leaderboard shows top traders ranked by:
- **Total Portfolio Value**: Cash + Holdings
- **Return %**: Percentage gain from initial $10,000

**Columns:**
| Rank | Username | Portfolio | Total Value | Return % |
|------|----------|-----------|-------------|----------|
| 1 | trader_pro | Main Portfolio | $12,500 | +25% |
| 2 | stockwhiz | My Trades | $11,200 | +12% |

### Making Your Portfolio Public

To appear on the leaderboard:
1. Your portfolio must be marked as **public**
2. Public portfolios are visible to all users
3. Only portfolio name and performance are shown (not individual holdings)

---

## Tips for Success

### Trading Strategies

1. **Diversify**: Don't put all your cash in one stock
2. **Research**: Check stock details before buying
3. **Watch Trends**: Use the price movement indicators
4. **Set Goals**: Decide your profit targets and loss limits

### Understanding Market Data

- **Prices update every 5 seconds** during market hours
- **After-hours**: Prices may be delayed or unchanged
- **Weekends/Holidays**: Markets are closed, no price updates

### Common Mistakes to Avoid

| Mistake | Solution |
|---------|----------|
| Buying at market open | Wait for prices to stabilize |
| Panic selling | Stick to your strategy |
| Ignoring fees | FinStream has no fees, but real trading does |
| Over-trading | Quality trades over quantity |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + Enter` | Submit form |
| `Escape` | Close dialog |

---

## Need Help?

- **API Documentation**: Check `/docs/API_DOCUMENTATION.md`
- **Troubleshooting**: Check `/docs/TROUBLESHOOTING.md`
- **GitHub Issues**: Report bugs or request features

---

*Happy Trading! 📈*
