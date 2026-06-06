"""Shared repository instances for API routes."""

from app.repository import CrudRepository
from app.models import (
    DeviceBasicInfo, SafetyCertInfo, MeasurePointInfo, MeasurePointRealtimeInfo,
    ObsoleteDeviceInfo, DeviceTestInfo, AlarmData,
)

basic_device_repo = CrudRepository[DeviceBasicInfo](
    "basic_devices", "device_name", DeviceBasicInfo,
    not_found_msg="设备不存在", duplicate_msg="设备名称已存在",
)
safety_cert_repo = CrudRepository[SafetyCertInfo](
    "safety_cert_list", "device_name", SafetyCertInfo,
    not_found_msg="安标信息不存在", duplicate_msg="该设备的安标信息已存在",
)
measure_point_repo = CrudRepository[MeasurePointInfo](
    "measure_point_list", "point_code", MeasurePointInfo,
    not_found_msg="测点不存在", duplicate_msg="测点编码已存在",
)
measure_point_realtime_repo = CrudRepository[MeasurePointRealtimeInfo](
    "measure_point_realtime_list", "point_code", MeasurePointRealtimeInfo,
    not_found_msg="测点实时信息不存在", duplicate_msg="测点实时信息已存在",
)
obsolete_device_repo = CrudRepository[ObsoleteDeviceInfo](
    "obsolete_device_list", "product_name", ObsoleteDeviceInfo,
    not_found_msg="淘汰设备信息不存在", duplicate_msg="该产品名称已存在",
)
device_test_repo = CrudRepository[DeviceTestInfo](
    "device_test_list", "factory_code", DeviceTestInfo,
    not_found_msg="检测检验信息不存在", duplicate_msg="该出厂编码已存在",
)
alarm_data_repo = CrudRepository[AlarmData](
    "alarm_data_list", "point_code", AlarmData,
    not_found_msg="异常数据不存在", duplicate_msg="该测点异常数据已存在",
)