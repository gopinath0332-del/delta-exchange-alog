
import time
from unittest.mock import MagicMock

def simulate_polling(client, order_id):
    """
    Simulation of the logic added to core/trading.py
    """
    max_attempts = 3
    order_details = None
    print(f"Starting simulation for Order ID: {order_id}")
    
    for attempt in range(max_attempts):
        # In actual code: time.sleep(2.0)
        # For test, we skip real sleep
        print(f"Polling for fill details (Attempt {attempt+1}/{max_attempts})...")
        try:
            order_details = client.get_order(order_id)
            if order_details and order_details.get('state') == 'closed':
                print(f"Order {order_id} confirmed CLOSED.")
                break
        except Exception as pe:
            print(f"Polling attempt {attempt+1} failed: {pe}")
            
    if order_details and order_details.get('state') == 'closed':
        print("Final Status: SUCCESS (Closed)")
        return True
    else:
        print("Final Status: TIMEOUT or FAILURE")
        return False

def test_successful_polling():
    print("\n--- Test 1: Order closes on 2nd attempt ---")
    mock_client = MagicMock()
    # 1st call: state='open', 2nd call: state='closed'
    mock_client.get_order.side_consecutive_calls = [
        {'id': 123, 'state': 'open'},
        {'id': 123, 'state': 'closed'}
    ]
    
    # Mocking side_effect to return values sequentially
    mock_client.get_order.side_effect = [
        {'id': 123, 'state': 'open'},
        {'id': 123, 'state': 'closed'}
    ]
    
    result = simulate_polling(mock_client, 123)
    assert result == True
    assert mock_client.get_order.call_count == 2

def test_timeout_polling():
    print("\n--- Test 2: Order never closes ---")
    mock_client = MagicMock()
    mock_client.get_order.side_effect = [
        {'id': 456, 'state': 'open'},
        {'id': 456, 'state': 'open'},
        {'id': 456, 'state': 'open'}
    ]
    
    result = simulate_polling(mock_client, 456)
    assert result == False
    assert mock_client.get_order.call_count == 3

if __name__ == "__main__":
    test_successful_polling()
    test_timeout_polling()
    print("\nAll simulations passed!")
