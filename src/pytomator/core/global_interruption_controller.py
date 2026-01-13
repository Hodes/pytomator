import threading

class GlobalInterruptionController:
    _global_threading_interrupt_event = None
    
    @classmethod
    def get_global_threading_interrupt_event(cls):
        if cls._global_threading_interrupt_event is None:
            cls._global_threading_interrupt_event = threading.Event()
        return cls._global_threading_interrupt_event
    
    @classmethod
    def request_global_interruption(cls):
        event = cls.get_global_threading_interrupt_event()
        event.set()
        
    @classmethod
    def clear_global_interruption(cls):
        event = cls.get_global_threading_interrupt_event()
        event.clear()
        
    @classmethod
    def is_global_interruption_requested(cls) -> bool:
        event = cls.get_global_threading_interrupt_event()
        return event.is_set()
    
def should_stop() -> bool:
    return GlobalInterruptionController.is_global_interruption_requested()