# Lark Bot Knowledge Transfer
*Understanding How Our Bot Works with Lark*

## What is Lark and Why We Use It

Lark is like Slack or Microsoft Teams - a workplace chat platform. Our company uses Lark for internal communication, so building our crypto monitoring bot here makes sense. Team members don't need to learn a new platform or install extra apps.

Think of Lark as the foundation where our bot lives and operates.

## How the Bot Connects to Lark

### The Basic Setup
When we created this bot, we registered it as an official "Lark App" in Lark's system. This is similar to how you might add a third-party app to Slack or Teams.

The registration gave us two important things:
- **App ID**: Like a username for our bot
- **App Secret**: Like a password for our bot

These credentials let our bot talk to Lark's servers securely.

### Where the Bot Lives
Our bot runs on our own servers, not on Lark's servers. When someone types a command in Lark, here's what happens:

1. User types `/check` in Lark chat
2. Lark sends this message to our bot server
3. Our bot processes the command and gets wallet balances
4. Our bot sends the results back to Lark
5. Results appear in the chat as a nice formatted card

This happens in about 3 seconds.

## Chat Organization in Lark

### Group Chat Structure
We use one main group chat with organized "topics" (like threads in Slack):

**#commands** - Where people type bot commands like `/check` and `/add`

**#daily-reports** - Where the bot posts automatic daily balance reports

**#quick-guide** - Optional help documentation

This organization keeps conversations tidy and makes it easy to find information.

### Why Topics Matter
When the bot responds, it knows exactly which topic to reply to. Commands go to the commands topic, reports go to the reports topic. This prevents our chat from becoming cluttered with mixed conversations.

## Security and Access Control

### How We Keep It Secure

**App-Level Security**: Our bot uses official Lark authentication. Every message between Lark and our bot is encrypted and verified.

**Server Security**: Our bot runs on secure servers with proper firewall protection. Only Lark can send messages to our bot.

**Code Security**: The bot validates every incoming message to ensure it's legitimate before processing any commands.

### User Authorization System

This is the most important part for daily operations.

**How Authorization Works**: Every Lark user has a unique ID (looks like `ou_1234567890abcdef`). Our bot maintains a list of authorized IDs. When someone sends a command, the bot checks if their ID is on the approved list.

**What Happens with Unauthorized Users**: If someone not on the list tries to use the bot, they get a polite message saying "Access Denied" along with their user ID. They can share this ID with an admin to request access.

**Managing Access**: To add or remove users, an admin updates the authorization list. Changes take effect immediately.

## Daily Operations

### For Regular Users
Once you're authorized, using the bot is simple. Type commands in the #commands topic and get immediate responses. The bot handles all the complexity behind the scenes.

### For Administrators
You have two main responsibilities:

**User Management**: Adding new team members to the authorized list when they join, removing them when they leave.

**Monitoring**: Keeping an eye on the daily reports to ensure everything is working normally.

## What Can Go Wrong and How to Fix It

### Bot Not Responding
This usually means our server is down or having connectivity issues. Check with the technical team.

### "Access Denied" Errors
The user isn't on the authorized list. Add their Lark ID to the system or verify they're using the correct account.

### Missing Daily Reports
Check if the scheduler is running properly. Contact technical support if reports stop appearing for more than one day.

### Wrong Data in Reports
This could be a blockchain connectivity issue or wallet configuration problem. Technical team should investigate.

## Getting New People Started

### For New Team Members
1. Admin adds them to the Lark group chat
2. Admin adds their Lark ID to the bot's authorized user list
3. They can immediately start using commands like `/help` and `/check`
4. No training or setup required on their end

### For New Administrators
1. Learn which team members should have access
2. Understand how to find and add Lark user IDs
3. Know who to contact for technical issues
4. Monitor daily reports for any irregularities

## Integration Benefits

### Why Lark Works Well for This
**Single Platform**: Team members already use Lark daily, so no new apps to learn.

**Rich Formatting**: Lark supports interactive cards with tables, colors, and organized layouts that make financial data easy to read.

**Topics**: Keep different types of conversations organized and easy to find.

**Mobile Access**: Works on phones, tablets, and computers seamlessly.

**Enterprise Security**: Lark handles user authentication, so we don't need separate login systems.

### Business Continuity
If our bot goes down temporarily, it doesn't affect Lark or other work. When it comes back online, everything resumes normally. The bot stores its configuration independently, so no data is lost.

## Key Takeaways

The bot integrates naturally with Lark because it was designed specifically for our team's workflow. Authorization is simple but secure - just managing a list of approved users. Daily operations require minimal oversight, and new users can start immediately once authorized.

The technical complexity is hidden from users, who just see a helpful tool that saves time and provides reliable financial data when they need it.