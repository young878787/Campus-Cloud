export interface OnCancel {
  readonly isResolved: boolean
  readonly isRejected: boolean
  readonly isCancelled: boolean
  (cancelHandler: () => void): void
}

export class CancelablePromise<T> implements Promise<T> {
  #isResolved = false
  #isRejected = false
  #isCancelled = false
  #cancelHandlers: Array<() => void> = []
  #promise: Promise<T>
  #reject?: (reason?: unknown) => void

  public constructor(
    executor: (
      resolve: (value: T | PromiseLike<T>) => void,
      reject: (reason?: unknown) => void,
      onCancel: OnCancel,
    ) => void,
  ) {
    this.#promise = new Promise<T>((resolve, reject) => {
      this.#reject = reject

      const onResolve = (value: T | PromiseLike<T>) => {
        if (this.#isResolved || this.#isRejected || this.#isCancelled) {
          return
        }
        this.#isResolved = true
        resolve(value)
      }

      const onReject = (reason?: unknown) => {
        if (this.#isResolved || this.#isRejected || this.#isCancelled) {
          return
        }
        this.#isRejected = true
        reject(reason)
      }

      const onCancel = ((cancelHandler: () => void) => {
        if (this.#isResolved || this.#isRejected || this.#isCancelled) {
          return
        }
        this.#cancelHandlers.push(cancelHandler)
      }) as OnCancel

      Object.defineProperty(onCancel, "isResolved", {
        get: () => this.#isResolved,
      })
      Object.defineProperty(onCancel, "isRejected", {
        get: () => this.#isRejected,
      })
      Object.defineProperty(onCancel, "isCancelled", {
        get: () => this.#isCancelled,
      })

      executor(onResolve, onReject, onCancel)
    })
  }

  public get [Symbol.toStringTag](): string {
    return "CancelablePromise"
  }

  public then<TResult1 = T, TResult2 = never>(
    onFulfilled?:
      | ((value: T) => TResult1 | PromiseLike<TResult1>)
      | null,
    onRejected?:
      | ((reason: unknown) => TResult2 | PromiseLike<TResult2>)
      | null,
  ): Promise<TResult1 | TResult2> {
    return this.#promise.then(onFulfilled, onRejected)
  }

  public catch<TResult = never>(
    onRejected?:
      | ((reason: unknown) => TResult | PromiseLike<TResult>)
      | null,
  ): Promise<T | TResult> {
    return this.#promise.catch(onRejected)
  }

  public finally(
    onFinally?: (() => void) | null,
  ): Promise<T> {
    return this.#promise.finally(onFinally ?? undefined)
  }

  public cancel(): void {
    if (this.#isResolved || this.#isRejected || this.#isCancelled) {
      return
    }

    this.#isCancelled = true

    for (const cancelHandler of this.#cancelHandlers) {
      try {
        cancelHandler()
      } catch {
        // Ignore cancellation handler failures.
      }
    }

    this.#cancelHandlers = []
    this.#reject?.(new Error("Request aborted"))
  }
}