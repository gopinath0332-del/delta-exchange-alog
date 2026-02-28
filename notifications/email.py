"""Email notification handler."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from core.config import Config
from core.logger import get_logger

logger = get_logger(__name__)


class EmailNotifier:
    """Handles sending email notifications via SMTP."""

    def __init__(self, config: Config):
        """
        Initialize Email notifier.

        Args:
            config: Configuration object containing email settings
        """
        self.config = config
        self.enabled = config.email_enabled
        
        # Load settings
        self.smtp_host = config.email_smtp_host
        self.smtp_port = config.email_smtp_port
        self.use_tls = config.email_use_tls
        self.username = config.email_username
        self.password = config.email_password
        self.from_addr = config.email_from
        self.recipients = config.email_recipients

    def send_email(self, subject: str, body: str, is_html: bool = False):
        """
        Send an email to configured recipients.

        Args:
            subject: Email subject
            body: Email body content
            is_html: True if body is HTML, False for plain text
        """
        if not self.config.email_enabled:
            return
            
        if not self.recipients or not self.username or not self.password:
            logger.warning("Email configuration incomplete, skipping email")
            return

        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.recipients)
            msg["Subject"] = subject

            # Attach body
            type_str = "html" if is_html else "plain"
            msg.attach(MIMEText(body, type_str))

            # Connect and send
            context = None
            if self.use_tls:
                try:
                    # Try to create default context (may fail on macOS)
                    context = ssl.create_default_context()
                    
                    # Try to load certifi certs if available
                    try:
                        import certifi
                        context.load_verify_locations(certifi.where())
                        logger.debug("Loaded SSL certificates from certifi")
                    except ImportError:
                        pass
                        
                except Exception as e:
                    logger.warning(f"Failed to create default SSL context: {e}, falling back to unverified context")
                    context = ssl._create_unverified_context()

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                # Basic connection
                # Upgrade to TLS
                if self.use_tls:
                    try:
                        server.starttls(context=context)
                    except ssl.SSLCertVerificationError:
                        logger.warning("SSL verification failed, retrying with unverified context")
                        context = ssl._create_unverified_context()
                        server.starttls(context=context)
                
                server.login(self.username, self.password)
                server.send_message(msg)
                
            logger.debug("Email sent successfully", subject=subject)

        except Exception as e:
            logger.error("Failed to send email", error=str(e))

    def send_trade_alert(self, 
                        symbol: str, 
                        side: str, 
                        price: float, 
                        rsi: float, 
                        reason: str,
                        margin_used: Optional[float] = None,
                        remaining_margin: Optional[float] = None,
                        strategy_name: Optional[str] = None,
                        pnl: Optional[float] = None,
                        funding_charges: Optional[float] = None,
                        trading_fees: Optional[float] = None,
                        market_price: Optional[float] = None,
                        lot_size: Optional[int] = None,
                        target_margin: Optional[float] = None):
        """
        Send a formatted trade alert email.

        Args:
            symbol: Trading symbol
            side: Trade action (ENTRY_LONG, EXIT_SHORT, etc.)
            price: Signal/fill price
            rsi: RSI indicator value at signal time
            reason: Human-readable reason for the signal
            margin_used: Actual margin consumed by the order
            remaining_margin: Wallet's available balance after the order
            strategy_name: Name of the strategy
            pnl: Realized PnL for exit signals
            funding_charges: Funding fees paid/received
            trading_fees: Commission fees
            market_price: Raw candle close price (if HA candle price differs)
            lot_size: Number of contracts placed
            target_margin: Configured target margin from .env (e.g. TARGET_MARGIN_PAXG=30)
        """
        subject = f"Trading Alert: {side} {symbol}"
        
        strategy_line = f"<li><strong>Strategy:</strong> {strategy_name}</li>" if strategy_name else ""
        lot_size_line = f"<li><strong>Lot Size:</strong> {lot_size} contracts</li>" if lot_size is not None else ""
        # Show the configured target margin so the recipient knows the capital allocation
        target_margin_line = f"<li><strong>Target Margin:</strong> ${target_margin:,.2f}</li>" if target_margin is not None else ""

        # HTML Body
        body = f"""
        <html>
          <body>
            <h2>Trading Signal Detected</h2>
            <ul>
              {strategy_line}
              <li><strong>Symbol:</strong> {symbol}</li>
              <li><strong>Side:</strong> <span style="color: {'green' if side == 'LONG' else 'red'}">{side}</span></li>
              <li><strong>Price:</strong> ${price:,.2f}</li>
              {lot_size_line}
              {target_margin_line}
              <li><strong>RSI:</strong> {rsi:.2f}</li>
              <li><strong>Reason:</strong> {reason}</li>
            </ul>
            <p>Sent from Delta Exchange Trading Bot</p>
          </body>
        </html>
        """
        
        self.send_email(subject, body, is_html=True)

    def send_status_message(self, title: str, message: str):
        """
        Send a status update email.
        """
        subject = f"Status Update: {title}"
        
        body = f"""
        <html>
          <body>
            <h2>{title}</h2>
            <p>{message}</p>
            <p>Sent from Delta Exchange Trading Bot</p>
          </body>
        </html>
        """
        self.send_email(subject, body, is_html=True)
