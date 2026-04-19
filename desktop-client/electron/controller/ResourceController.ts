import Logger from "../core/Logger";
import CampusCloudService from "../service/CampusCloudService";
import ResponseUtils from "../utils/ResponseUtils";
import BaseController from "./BaseController";

class ResourceController extends BaseController {
  private readonly _campusCloudService: CampusCloudService;

  constructor(campusCloudService: CampusCloudService) {
    super();
    this._campusCloudService = campusCloudService;
  }

  listMyResources(req: ControllerParam) {
    this._campusCloudService
      .listResources()
      .then(data => {
        req.event.reply(req.channel, ResponseUtils.success(data));
      })
      .catch((err: Error) => {
        Logger.error("ResourceController.listMyResources", err);
        req.event.reply(req.channel, ResponseUtils.fail(err));
      });
  }
}

export default ResourceController;
