import os
import sys
import signal
import logging
import pandas as pd
from datetime import datetime

# Ajout du dossier common au path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.binance_client import BinanceClient
from common.indicators import TechnicalIndicators
from common.utils import print_trading_info, safe_sleep

class BinanceRSIBot:
    def __init__(self):
        # Configuration du logging
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'rsi_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        
        # Initialisation du client Binance
        self.client = BinanceClient()
        
        # Configuration du trading
        self.symbol = 'BTCUSDT'
        self.interval = '5m'
        self.rsi_period = 14
        self.rsi_overbought = 70
        self.rsi_oversold = 30
        
        # Paramètres OCO
        self.stop_loss_percent = 2.0  # Stop-loss à 2% en dessous du prix d'achat
        self.take_profit_percent = 6.0  # Take-profit à 6% au-dessus du prix d'achat
        
        # Configuration du trailing stop
        self.trailing_stop_percent = 5.0  # Distance en pourcentage pour le trailing stop
        self.trailing_stop_activation = 2.0  # Pourcentage de gain minimum pour activer le trailing stop
        
        # État du bot
        self.in_position = False
        self.last_price = None
        self.current_oco_order = None  # Pour stocker l'ID de l'ordre OCO actuel
        self.active_positions = {}  # Pour suivre les positions et leurs trailing stops
        self.running = True
        
        # Configuration des signaux
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        
        self.logger.info(f"Bot RSI initialisé avec:")
        self.logger.info(f"- Période RSI: {self.rsi_period}")
        self.logger.info(f"- Seuils RSI: Survente={self.rsi_oversold}, Surachat={self.rsi_overbought}")
        self.logger.info(f"- Stop-loss: {self.stop_loss_percent}%")
        self.logger.info(f"- Take-profit: {self.take_profit_percent}%")
        self.logger.info(f"- Trailing stop: {self.trailing_stop_percent}% après {self.trailing_stop_activation}% de gain")
    
    def _handle_signal(self, signum, frame):
        """Gestion des signaux d'arrêt"""
        self.logger.info(f"Signal {signum} reçu, arrêt du bot...")
        self.running = False
    
    def _update_trailing_stops(self):
        """Met à jour les trailing stops pour toutes les positions actives"""
        try:
            for pair, position in list(self.active_positions.items()):
                # Récupération du prix actuel
                ticker = self.client.get_symbol_ticker(symbol=pair)
                current_price = float(ticker['price'])
                
                # Calcul du gain en pourcentage
                entry_price = position['entry_price']
                gain_percent = ((current_price - entry_price) / entry_price) * 100
                
                # Si le gain dépasse le seuil d'activation
                if gain_percent >= self.trailing_stop_activation:
                    # Calcul du nouveau stop price
                    new_stop_price = current_price * (1 - self.trailing_stop_percent/100)
                    
                    # Si le nouveau stop est plus haut que l'ancien, on le met à jour
                    if new_stop_price > position['stop_price']:
                        try:
                            # Annuler l'ancien ordre stop
                            if 'stop_order_id' in position:
                                self.client.cancel_order(
                                    symbol=pair,
                                    orderId=position['stop_order_id']
                                )
                            
                            # Placer le nouveau stop
                            stop_order = self.client.create_order(
                                symbol=pair,
                                side='SELL',
                                type='STOP_LOSS_LIMIT',
                                timeInForce='GTC',
                                quantity=position['quantity'],
                                stopPrice=str(new_stop_price),
                                price=str(new_stop_price * 0.99)
                            )
                            
                            # Mettre à jour la position
                            self.active_positions[pair]['stop_price'] = new_stop_price
                            self.active_positions[pair]['stop_order_id'] = stop_order['orderId']
                            self.active_positions[pair]['highest_price'] = current_price
                            
                            self.logger.info(f"Trailing stop mis à jour pour {pair}: {new_stop_price} (gain: {gain_percent:.2f}%)")
                            
                        except Exception as e:
                            self.logger.error(f"Erreur lors de la mise à jour du trailing stop pour {pair}: {e}")
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour des trailing stops: {e}")
    
    def run(self):
        """Fonction principale du bot"""
        self.logger.info(f"Démarrage du bot RSI pour {self.symbol}")
        self.logger.info(f"Paramètres OCO: Stop-loss: {self.stop_loss_percent}%, Take-profit: {self.take_profit_percent}%")
        
        while self.running:
            try:
                # Récupération des données
                klines = self.client.get_historical_klines(
                    self.symbol,
                    self.interval,
                    "1 day ago UTC"
                )
                
                if klines is None:
                    safe_sleep(60)
                    continue
                
                # Conversion en DataFrame
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume',
                    'ignore'
                ])
                df['close'] = df['close'].astype(float)
                
                # Calcul des indicateurs
                rsi = TechnicalIndicators.calculate_rsi(df['close'], self.rsi_period)
                current_price = float(df['close'].iloc[-1])
                
                # Affichage des informations
                self.logger.info(f"Prix actuel: {current_price}, RSI: {rsi}")
                
                # Logique de trading
                if not self.in_position and rsi < self.rsi_oversold:
                    # Calcul de la quantité à acheter
                    usdt_balance = self.client.get_account_balance('USDT')
                    quantity = (usdt_balance * 0.95) / current_price
                    quantity = round(quantity, 6)
                    
                    if quantity > 0:
                        self.logger.info(f"Signal d'achat détecté - RSI: {rsi}")
                        if self.client.execute_trade(self.symbol, 'BUY', quantity):
                            self.in_position = True
                            self.last_price = current_price
                            
                            # Placer l'ordre OCO
                            stop_price = self.last_price * (1 - self.stop_loss_percent/100)
                            stop_limit_price = stop_price * 0.99  # 1% en dessous du stop
                            take_profit_price = self.last_price * (1 + self.take_profit_percent/100)
                            
                            oco_order = self.client.place_oco_order(
                                symbol=self.symbol,
                                side='SELL',
                                quantity=quantity,
                                stop_price=stop_price,
                                stop_limit_price=stop_limit_price,
                                take_profit_price=take_profit_price
                            )
                            if oco_order:
                                self.current_oco_order = oco_order
                                self.logger.info(f"Ordre OCO placé - Stop: {stop_price}, Take-profit: {take_profit_price}")
                                
                                # Enregistrer la position pour le trailing stop
                                self.active_positions[self.symbol] = {
                                    'entry_price': self.last_price,
                                    'quantity': quantity,
                                    'stop_price': stop_price,
                                    'stop_order_id': oco_order['orderListId'],
                                    'highest_price': self.last_price
                                }
                
                elif self.in_position and rsi > self.rsi_overbought:
                    # Vendre la totalité de la position
                    btc_balance = self.client.get_account_balance('BTC')
                    if btc_balance > 0:
                        self.logger.info(f"Signal de vente détecté - RSI: {rsi}")
                        
                        # Annuler l'ordre OCO existant avant de vendre
                        if self.current_oco_order:
                            try:
                                self.client.cancel_order_by_id(
                                    symbol=self.symbol,
                                    order_id=self.current_oco_order['orderListId']
                                )
                                self.logger.info("Ordre OCO annulé")
                            except Exception as e:
                                self.logger.error(f"Erreur lors de l'annulation de l'ordre OCO: {e}")
                        
                        if self.client.execute_trade(self.symbol, 'SELL', btc_balance):
                            self.in_position = False
                            self.last_price = None
                            self.current_oco_order = None
                            if self.symbol in self.active_positions:
                                del self.active_positions[self.symbol]
                
                # Mise à jour des trailing stops
                self._update_trailing_stops()
                
                safe_sleep(60)
                
            except Exception as e:
                self.logger.error(f"Erreur inattendue: {e}")
                safe_sleep(60)
        
        self.logger.info("Bot arrêté proprement")

if __name__ == "__main__":
    bot = BinanceRSIBot()
    bot.run() 
