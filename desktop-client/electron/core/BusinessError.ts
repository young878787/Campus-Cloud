enum ResponseCode {
  SUCCESS = "A1000;successful.",
  INTERNAL_ERROR = "B1000;internal error.",
  NOT_LOGGED_IN = "B1001;Not logged in.",
  LOGIN_TIMEOUT = "B1002;Login timed out.",
  NO_TUNNELS = "B1003;No tunnels available.",
  FRPC_BINARY_MISSING = "B1004;frpc binary not found.",
  BACKEND_ERROR = "B1005;Backend request failed."
}

class BusinessError extends Error {
  private readonly _bizCode: string;

  constructor(bizErrorEnum: ResponseCode, detail?: string) {
    const [bizCode, message] = bizErrorEnum.split(";");
    super(detail ? `${message} ${detail}` : message);
    this._bizCode = bizCode;
    this.name = "BusinessError";
  }

  get bizCode(): string {
    return this._bizCode;
  }
}

export { BusinessError, ResponseCode };
