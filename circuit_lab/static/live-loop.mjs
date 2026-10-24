// At most one task in flight. Resume waits for an older task to finish;
// every new task reads the latest frame rather than queuing camera frames.
export class LiveLoop {
  constructor(task, delay = 750) {
    this.task = task;
    this.delay = delay;
    this.enabled = false;
    this.running = false;
    this.generation = 0;
    this.timer = null;
  }
  start(initialDelay = 0) {
    if (this.enabled) return;
    this.enabled = true;
    this.generation++;
    if (initialDelay > 0) this.timer = setTimeout(() => this.tick(), initialDelay);
    else this.tick();
  }
  stop() {
    this.enabled = false;
    this.generation++;
    clearTimeout(this.timer);
    this.timer = null;
  }
  async tick() {
    if (!this.enabled || this.running) return;
    this.running = true;
    const generation = this.generation;
    try {
      await this.task(() => this.enabled && generation === this.generation);
    } finally {
      this.running = false;
      if (this.enabled) this.timer = setTimeout(() => this.tick(), this.delay);
    }
  }
}
