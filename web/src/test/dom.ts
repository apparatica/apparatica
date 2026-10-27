// What jsdom lacks and Radix UI and cmdk use: element sizes, pointer capture, scrolling into view.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ResizeObserverStub;
Element.prototype.scrollIntoView ??= function () {};
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= function () {};
Element.prototype.releasePointerCapture ??= function () {};
