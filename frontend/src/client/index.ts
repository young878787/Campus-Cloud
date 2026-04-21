export * from "./types.gen"

export { ApiError } from "./core/ApiError"
export type { ApiRequestOptions } from "./core/ApiRequestOptions"
export type { ApiResult } from "./core/ApiResult"
export { CancelablePromise } from "./core/CancelablePromise"
export { OpenAPI } from "./core/OpenAPI"
export type { OpenAPIConfig } from "./core/OpenAPI"
export { request } from "./core/request"

export {
	AuditLogsService,
	AiTemplateRecommendationService,
	DeletionRequestsService,
	GroupsService,
	LoginService,
	LxcService,
	ResourceDetailsService,
	ResourcesService,
	ScriptDeployService,
	SpecChangeRequestsService,
	UsersService,
	VmRequestsService,
	VmService,
} from "./compat"
export type {
	BatchActionResponse,
	BatchActionResultItem,
	DeletionRequestCreated,
	DeletionRequestPublic,
	DeletionRequestsPublic,
	DeletionRequestStatus,
} from "./compat"

export {
	AiApiService,
	AiProxyService,
	AiPveAdvisorService,
	BatchProvisionService,
	CloudflareService,
	DesktopClientService,
	FirewallService,
	GatewayService,
	MigrationJobsService,
	type Options,
	PrivateService,
	ProxmoxConfigService,
	ReverseProxyService,
	RubricService,
	TunnelService,
	UtilsService,
} from "./sdk.gen"

export type Body_login_login_access_token =
	import("./types.gen").BodyLoginLoginAccessToken
export type LXCCreateRequest = import("./types.gen").LxcCreateRequest
export type LXCCreateResponse = import("./types.gen").LxcCreateResponse
export type VMCreateRequest = import("./types.gen").VmCreateRequest
export type VMCreateResponse = import("./types.gen").VmCreateResponse
export type VMRequestCreate = import("./types.gen").VmRequestCreate
export type VMRequestPublic = import("./types.gen").VmRequestPublic
export type VMRequestReview = import("./types.gen").VmRequestReview
export type VMRequestsPublic = import("./types.gen").VmRequestsPublic
export type VMRequestStatus = import("./types.gen").VmRequestStatus
export type VMTemplateSchema = import("./types.gen").VmTemplateSchema
export type VNCInfoSchema = import("./types.gen").VncInfoSchema
