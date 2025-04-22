import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_price_alert(user_email: str, product_title: str, current_price: float, target_price: float, product_url: str) -> bool:
    """
    Send a price alert email to the user.
    
    Args:
        user_email (str): Recipient's email address
        product_title (str): Name of the product
        current_price (float): Current price of the product
        target_price (float): Target price set by the user
        product_url (str): URL of the product
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Get email credentials from environment variables
        sender_email = os.getenv("EMAIL_ADDRESS")
        sender_password = os.getenv("EMAIL_PASSWORD")
        
        if not sender_email or not sender_password:
            logger.error("Email credentials not found in environment variables")
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = user_email
        msg["Subject"] = f"Price Alert: {product_title} is now ${current_price:.2f}!"
        
        # Create email body
        body = f"""
        Good news! The price for {product_title} has dropped below your target price.
        
        Current Price: ${current_price:.2f}
        Your Target Price: ${target_price:.2f}
        
        You can view the product here:
        {product_url}
        
        Happy shopping!
        
        Best regards,
        Your Price Tracker
        """
        
        msg.attach(MIMEText(body, "plain"))
        
        # Create SMTP session
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info(f"Price alert email sent successfully to {user_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send price alert email: {str(e)}")
        return False 