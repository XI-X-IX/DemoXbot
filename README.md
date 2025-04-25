# Démo

**Démo** d'un bot de trading automatisé pour Binance utilisant l'indicateur **RSI (Relative Strength Index)** pour prendre des décisions d'achat et de vente sur la paire **BTC/USDT**.

<br>

> **ATTENTION** : Ceci est une **démo (early stage)** /!\ **Ne pas l'utiliser tel quel**. Des ajustements et des tests sont nécessaires avant une utilisation en conditions réelles.

 <br><br>

## Fonctionnement du Bot

### 1. **Initialisation**

- Le bot se connecte à l'API Binance via `BinanceClient`.
- Il est configuré avec des paramètres de trading, incluant :
  - **RSI**
  - **Stop-loss**
  - **Take-profit**
  - **Trailing stop**

### 2. **Logiciel RSI**

Chaque minute, le bot récupère les données de marché de la paire **BTC/USDT** (intervalle de 5 minutes).  
Le **RSI** est calculé pour identifier les conditions suivantes :
  - **Surachat** (RSI > 70)
  - **Survente** (RSI < 30)

### 3. **Stratégie de Trading**

- **Achat** :  
  Si le **RSI** est inférieur à 30 (survente), le bot achète une quantité de **BTC** avec **95%** de son solde **USDT** disponible.  
  Un ordre **OCO** (One Cancels Other) est ensuite placé, comprenant :
  - **Stop-loss**
  - **Take-profit**

- **Vente** :  
  Si le **RSI** est supérieur à 70 (surachat), le bot vend le **BTC** détenu et annule tout ordre **OCO** existant.

### 4. **Trailing Stop**

Si une position est ouverte, le bot met à jour dynamiquement le **trailing stop** lorsque le prix du **BTC** augmente, afin de sécuriser les gains.

### 5. **Gestion des Signaux**

Le bot écoute les signaux de terminaison du processus (`SIGINT`, `SIGTERM`) pour s'arrêter proprement.

---
