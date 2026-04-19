import BeanFactory from "../core/BeanFactory";
import Logger from "../core/Logger";
import SystemService from "../service/SystemService";
import PathUtils from "../utils/PathUtils";
import ResponseUtils from "../utils/ResponseUtils";
import BaseController from "./BaseController";

class SystemController extends BaseController {
  private readonly _systemService: SystemService;

  constructor() {
    super();
    this._systemService = BeanFactory.getBean("systemService");
  }

  openUrl(req: ControllerParam) {
    this._systemService
      .openUrl(req.args?.url)
      .then(() => {
        req.event.reply(req.channel, ResponseUtils.success());
      })
      .catch((err: Error) => {
        Logger.error("SystemController.openUrl", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }

  relaunchApp(req: ControllerParam) {
    this._systemService
      .relaunch()
      .then(() => {
        req.event.reply(req.channel, ResponseUtils.success());
      })
      .catch((err: Error) => {
        Logger.error("SystemController.relaunchApp", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }

  openAppData(req: ControllerParam) {
    this._systemService
      .openLocalPath(PathUtils.getAppData())
      .then(() => {
        req.event.reply(req.channel, ResponseUtils.success());
      })
      .catch((err: Error) => {
        Logger.error("SystemController.openAppData", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }

  openSsh(req: ControllerParam) {
    const port = Number(req.args?.port);
    if (!Number.isFinite(port) || port <= 0) {
      req.event.reply(
        req.channel,
        ResponseUtils.fail(new Error("invalid port"))
      );
      return;
    }
    this._systemService
      .openSsh(port)
      .then(() => {
        req.event.reply(req.channel, ResponseUtils.success());
      })
      .catch((err: Error) => {
        Logger.error("SystemController.openSsh", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }
}

export default SystemController;
