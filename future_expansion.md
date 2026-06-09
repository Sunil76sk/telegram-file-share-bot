# Telegram File Share Bot — Future Expansion Roadmap

This document outlines the current implementation status and technical blueprint for the advanced features listed in the roadmap.

---

## 📊 Current Roadmap Status

| Feature | Codebase Status | Description |
| :--- | :--- | :--- |
| **Referral Program** | **✅ Fully Implemented** | Points reward system and referral links via `/referral`. |
| **Content Subscription System** | **✅ Fully Implemented** | Tiered subscription levels (Silver & Gold) with Stars / UPI. |
| **White Label SaaS Platform** | **✅ Fully Implemented** | Multi-tenant bot builder (`/createbot`, `saas.py` runner). |
| **Creator Marketplace** | **⚠️ Partially Implemented** | Store catalog (`/store`) is ready; needs multi-creator seller onboarding. |
| **Affiliate Marketplace** | **⚠️ Partially Implemented** | Shorteners and sponsored pages are ready; needs product referral tracking. |
| **Telegram Mini App** | **🚀 Planned** | Frontend UI for store, ads, and sub-bot builders. |
| **AI Recommendation Engine** | **🚀 Planned** | AI-driven content and ad matching. |

---

## 🛠 Technical Blueprints for Planned Features

### 1. Telegram Mini App (TMA)
* **Goal**: Provide a premium, swipeable WebApp interface inside Telegram for the store (`/store`), ad tracking, and the SaaS bot builder panel.
* **Architecture**:
  - **Frontend**: A React + Vite or Next.js application styled with TailwindCSS (using Telegram WebApp CSS variables for auto-theme matching).
  - **Backend Integration**: Create a small FastAPI or Flask API server sharing the same MongoDB database, verifying requests using the Telegram WebApp `initData` hash check.
  - **Bot Command**: `/app` opens the WebApp view within Telegram.

### 2. AI Recommendation Engine
* **Goal**: Maximize CTR on shortened links and store items by showing personalized recommendations based on past user downloads.
* **Architecture**:
  - Use MongoDB aggregation or standard vector embeddings (via OpenAI/Gemini embeddings) to match user download histories with similar catalog items.
  - Run a periodic background task to calculate user preferences and suggest relative content during the waiting countdown screens.

### 3. Creator & Affiliate Marketplace Scale-up
* **Goal**: Allow third-party creators to list files in the `/store` and affiliate marketers to earn a commission for driving sales.
* **Architecture**:
  - **Multi-Vendor Store**: Extend `premium_catalog_col` to include a `seller_id` field. Release payments to the seller while withholding a platform commission fee (similar to the SaaS sub-bot platform fee).
  - **Affiliate Tracking**: Introduce an `affiliate_id` query parameter to store links (e.g. `start=store_item_123_aff_456`). If purchased, automatically distribute the configured commission percentage to the affiliate's balance.
