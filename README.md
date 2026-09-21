# 🤖 SolvIIT — Competitive Programming Leaderboard Telegram Bot

<p align="center">
  <b>The official automated LeetCode tracking bot for SolvIIT</b><br>
  <i>Competitive Programming & Technical Interview Preparation Club — ETSIIT, Universidad de Granada</i>
</p>

---

## 📌 Overview

**SolvIIT Bot** is a self-hosted Telegram bot built to drive engagement, healthy competition, and consistency within student competitive programming groups. 

Instead of only tracking lifetime problem counts—which discourages newer members—the bot monitors **weekly deltas** (new problems solved and contest rating gains), leveling the playing field and keeping everyone motivated week over week.

---

## ✨ Features

* **⚡ Zero-API-Key Scraping:** Direct integration with LeetCode's public GraphQL API for problem counts and official contest ratings.
* **📈 Delta-Based Rankings:** Computes weekly net progress ($\Delta \text{Solved}$ by difficulty, $\Delta \text{Rating}$) so recent effort is rewarded over legacy solve counts.
* **⏰ Automated Weekly Broadcasts:** Automatically runs a snapshot job every Sunday night and posts the club leaderboard directly to the Telegram group.
* **💾 Lightweight SQLite Storage:** Zero-configuration local database persisted safely via Docker volumes.
* **🐳 One-Click Docker Setup:** Ready to run out of the box with Docker Compose on any server or local machine.

---