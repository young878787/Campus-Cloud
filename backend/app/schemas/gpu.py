"""GPU resource mapping schemas."""

from pydantic import BaseModel, Field


class GPUDeviceMap(BaseModel):
    """A single node-level mapping entry for a GPU resource mapping."""

    node: str
    path: str
    id: str = ""
    subsystem_id: str | None = None
    iommu_group: int | None = None
    description: str | None = None
    is_mdev: bool = False


class GPUMappingPublic(BaseModel):
    """Public representation of a PVE PCI resource mapping (GPU)."""

    id: str = Field(description="Mapping logical ID (name)")
    description: str = ""
    maps: list[GPUDeviceMap] = Field(default_factory=list)


class GPUMappingDetail(GPUMappingPublic):
    """Detail view with usage information."""

    physical_gpu_count: int = Field(default=0, description="Estimated physical GPU count (by unique PCI bus)")
    device_count: int = Field(default=0, description="Total assignable device/VF slots")
    used_count: int = 0
    available_count: int = 0
    is_sriov: bool = Field(default=False, description="True if SR-IOV detected (multiple devices on same PCI bus)")
    has_mdev: bool = Field(default=False, description="True if any device uses mediated devices")
    total_vram_mb: int = Field(default=0, description="Total physical VRAM in MB")
    used_vram_mb: int = Field(default=0, description="Allocated VRAM in MB (sum of assigned vGPU/passthrough)")
    used_by: list["GPUUsageInfo"] = Field(default_factory=list)


class GPUUsageInfo(BaseModel):
    """Information about a VM using a GPU mapping."""

    vmid: int
    vm_name: str = ""
    node: str = ""
    status: str = ""
    mdev_type: str = ""
    allocated_vram_mb: int = 0


class GPUMappingsPublic(BaseModel):
    """List of GPU mappings."""

    data: list[GPUMappingDetail]
    count: int


class GPUMappingCreate(BaseModel):
    """Create a new PCI resource mapping."""

    id: str = Field(min_length=1, max_length=128, description="Mapping name")
    description: str = ""
    map: list[str] = Field(
        min_length=1,
        description="List of map entries, e.g. 'node=pve1,path=0000:01:00.0'",
    )


class GPUMappingUpdate(BaseModel):
    """Update an existing PCI resource mapping."""

    description: str | None = None
    map: list[str] | None = None


class GPUSummary(BaseModel):
    """A simplified GPU option for the application form selector."""

    mapping_id: str
    description: str = ""
    model: str = ""
    vram: str = ""
    node: str = ""
    physical_gpu_count: int = 1
    device_count: int = 1
    used_count: int = 0
    available_count: int = 1
    is_sriov: bool = False
    has_mdev: bool = False
    total_vram_mb: int = 0
    used_vram_mb: int = 0
