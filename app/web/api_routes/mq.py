"""MQTT/Message Queue API routes."""

import logging

from fastapi import APIRouter, HTTPException

from app.config import load_config

router = APIRouter(prefix="/mq", tags=["mq"])
logger = logging.getLogger(__name__)


@router.post("/publish/{data_type}")
async def mq_publish(data_type: str, backend: str = "log"):
    """通过消息队列发布单个报文。

    backend: log (默认，写入本地文件) | rabbitmq
    """
    from app.formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        SYSTEM_MAP,
    )
    from app.mq_uploader import create_mq_uploader, QUEUE_MAP

    config = load_config()
    system_info = config.system_info

    formatter_map = {
        "jbsj": lambda si=system_info: format_jbsj(config.basic_devices, si),
        "absj": lambda si=system_info: format_absj(config.safety_cert_list, si),
        "jztt": lambda si=system_info: format_jztt(config.obsolete_device_list, si),
        "jcjy": lambda si=system_info: format_jcjy(config.device_test_list, si),
    }
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        formatter_map[f"{prefix}jc"] = lambda sk=sys_key, si=system_info: format_system_jc(
            config.measure_point_list, sk, si
        )
        formatter_map[f"{prefix}ss"] = lambda sk=sys_key, si=system_info: format_system_ss(
            config.measure_point_realtime_list, sk, si
        )
        formatter_map[f"{prefix}yc"] = lambda sk=sys_key, si=system_info: format_system_yc(
            config.alarm_data_list, sk, si
        )

    if data_type not in formatter_map:
        raise HTTPException(status_code=400, detail=f"不支持的数据类型: {data_type}")

    content = formatter_map[data_type]()
    uploader = create_mq_uploader(backend)
    await uploader.connect()
    success = await uploader.publish_report(data_type, content)
    await uploader.disconnect()

    if success:
        return {"status": "success", "queue": QUEUE_MAP.get(data_type.lower(), ""), "data_type": data_type}
    return {"status": "error", "message": "发布失败"}


@router.post("/publish-all")
async def mq_publish_all(backend: str = "log"):
    """批量发布所有报文到消息队列。"""
    from app.formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        SYSTEM_MAP,
    )
    from app.mq_uploader import create_mq_uploader

    config = load_config()
    system_info = config.system_info
    uploader = create_mq_uploader(backend)
    await uploader.connect()

    reports = {
        "jbsj": format_jbsj(config.basic_devices, system_info),
        "absj": format_absj(config.safety_cert_list, system_info),
        "jztt": format_jztt(config.obsolete_device_list, system_info),
        "jcjy": format_jcjy(config.device_test_list, system_info),
    }
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        reports[f"{prefix}jc"] = format_system_jc(config.measure_point_list, sys_key, system_info)
        reports[f"{prefix}ss"] = format_system_ss(config.measure_point_realtime_list, sys_key, system_info)
        reports[f"{prefix}yc"] = format_system_yc(config.alarm_data_list, sys_key, system_info)

    results = await uploader.publish_all(reports)
    await uploader.disconnect()

    success_count = sum(1 for v in results.values() if v)
    return {"status": "success", "published": success_count, "total": len(results), "results": results}