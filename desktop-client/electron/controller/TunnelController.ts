import Logger from "../core/Logger";
import FrpcProcessService from "../service/FrpcProcessService";
import ResponseUtils from "../utils/ResponseUtils";
import BaseController from "./BaseController";

class TunnelController extends BaseController {
  private readonly _frpcProcessService: FrpcProcessService;

  constructor(frpcProcessService: FrpcProcessService) {
    super();
    this._frpcProcessService = frpcProcessService;
  }

  start(req: ControllerParam) {
    this._frpcProcessService
      .startTunnel()
      .then(() => {
        req.event.reply(req.channel, ResponseUtils.success());
      })
      .catch((err: Error) => {
        Logger.error("TunnelController.start", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }

  stop(req: ControllerParam) {
    this._frpcProcessService
      .stopTunnel()
      .then(() => {
        req.event.reply(req.channel, ResponseUtils.success());
      })
      .catch((err: Error) => {
        Logger.error("TunnelController.stop", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }

  getStatus(req: ControllerParam) {
    const running = this._frpcProcessService.isRunning();
    const connectionError = running
      ? this._frpcProcessService.readFrpcConnectionError()
      : null;
    const status: TunnelStatusInfo = {
      running,
      lastStartTime: this._frpcProcessService.frpcLastStartTime,
      connectionError,
      tunnels: this._frpcProcessService.tunnels
    };
    req.event.reply(req.channel, ResponseUtils.success(status));
  }
}

export default TunnelController;
