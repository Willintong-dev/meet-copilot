import queue
import threading


class EventBus:
    def __init__(self):
        self.subscribers = []
        self.history = []
        self.lock = threading.Lock()

    def publish(self, kind, payload):
        event = {"type": kind, "data": payload}
        with self.lock:
            self.history.append(event)
            subscribers = list(self.subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def subscribe(self):
        subscriber = queue.Queue()
        with self.lock:
            for event in self.history:
                subscriber.put(event)
            self.subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber):
        with self.lock:
            if subscriber in self.subscribers:
                self.subscribers.remove(subscriber)

    def clear_history(self):
        with self.lock:
            self.history = []
