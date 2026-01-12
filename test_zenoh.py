import zenoh
import time

def test_pubsub():
    """Simple test to verify Zenoh is working."""
    received = []
    
    def listener(sample):
        received.append(sample.payload.to_string())
    
    config = zenoh.Config()
    with zenoh.open(config) as session:
        # Subscribe
        sub = session.declare_subscriber('test/hello', listener)
        
        # Publish
        session.put('test/hello', 'Hello Zenoh!')
        
        # Wait for message
        time.sleep(0.5)
        
        assert len(received) == 1
        assert received[0] == 'Hello Zenoh!'
        print("✓ Zenoh pub/sub working!")

if __name__ == '__main__':
    test_pubsub()
