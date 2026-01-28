"""
Telemetry recording mixin for openTPT.

Provides telemetry data collection and recording functionality.
"""

import logging
import time

from utils.telemetry_recorder import TelemetryFrame

logger = logging.getLogger('openTPT.telemetry')


class TelemetryMixin:
    """Mixin providing telemetry recording methods."""

    def _record_telemetry_frame(self):
        """Record a single frame of telemetry data at configured rate."""
        if not self.recorder.is_recording():
            return

        # Rate limit recording to RECORDING_RATE_HZ (default 10 Hz)
        current_time = time.time()
        if current_time - self.last_recording_time < self.recording_interval:
            return
        self.last_recording_time = current_time

        frame = TelemetryFrame(timestamp=current_time)

        # TPMS data
        tpms_data = self.tpms.get_data()
        for position, data in tpms_data.items():
            pressure = data.get("pressure")
            temp = data.get("temp")
            if position == "FL":
                frame.tpms_fl_pressure = pressure
                frame.tpms_fl_temp = temp
            elif position == "FR":
                frame.tpms_fr_pressure = pressure
                frame.tpms_fr_temp = temp
            elif position == "RL":
                frame.tpms_rl_pressure = pressure
                frame.tpms_rl_temp = temp
            elif position == "RR":
                frame.tpms_rr_pressure = pressure
                frame.tpms_rr_temp = temp

        # Tyre thermal data (3-zone temps from CAN corner sensors)
        if self.thermal:
            for position in ["FL", "FR", "RL", "RR"]:
                zone_data = self.thermal.get_zone_data(position)
                if zone_data:
                    # Zone data has left_median, centre_median, right_median
                    inner = zone_data.get("left_median")
                    centre = zone_data.get("centre_median")
                    outer = zone_data.get("right_median")
                    if position == "FL":
                        frame.tyre_fl_inner = inner
                        frame.tyre_fl_centre = centre
                        frame.tyre_fl_outer = outer
                    elif position == "FR":
                        frame.tyre_fr_inner = inner
                        frame.tyre_fr_centre = centre
                        frame.tyre_fr_outer = outer
                    elif position == "RL":
                        frame.tyre_rl_inner = inner
                        frame.tyre_rl_centre = centre
                        frame.tyre_rl_outer = outer
                    elif position == "RR":
                        frame.tyre_rr_inner = inner
                        frame.tyre_rr_centre = centre
                        frame.tyre_rr_outer = outer

        # Brake temps
        if self.brakes:
            brake_temps = self.brakes.get_temps()
            for position, data in brake_temps.items():
                temp = data.get("temp") if isinstance(data, dict) else data
                if position == "FL":
                    frame.brake_fl = temp
                elif position == "FR":
                    frame.brake_fr = temp
                elif position == "RL":
                    frame.brake_rl = temp
                elif position == "RR":
                    frame.brake_rr = temp

        # IMU data
        if self.imu:
            imu_snapshot = self.imu.get_data()
            if imu_snapshot:
                frame.accel_x = imu_snapshot.get("accel_x")
                frame.accel_y = imu_snapshot.get("accel_y")
                frame.accel_z = imu_snapshot.get("accel_z")
                frame.gyro_x = imu_snapshot.get("gyro_x")
                frame.gyro_y = imu_snapshot.get("gyro_y")
                frame.gyro_z = imu_snapshot.get("gyro_z")

        # OBD2 data
        if self.obd2:
            obd_snapshot = self.obd2.get_data()
            if obd_snapshot:
                frame.obd_speed_kmh = obd_snapshot.get("obd_speed_kmh")
                frame.engine_rpm = obd_snapshot.get("engine_rpm")
                frame.throttle_percent = obd_snapshot.get("throttle_percent")
                frame.coolant_temp_c = obd_snapshot.get("coolant_temp_c")
                frame.oil_temp_c = obd_snapshot.get("oil_temp_c")
                frame.intake_temp_c = obd_snapshot.get("intake_temp_c")
                frame.map_kpa = obd_snapshot.get("map_kpa")
                frame.boost_kpa = obd_snapshot.get("boost_kpa")
                frame.maf_gs = obd_snapshot.get("maf_gs")
                frame.battery_soc = obd_snapshot.get("battery_soc")
                frame.brake_pressure_input_bar = obd_snapshot.get("brake_pressure_input_bar")
                frame.brake_pressure_output_bar = obd_snapshot.get("brake_pressure_output_bar")

        # GPS data
        if self.gps:
            gps_snapshot = self.gps.get_snapshot()
            if gps_snapshot and gps_snapshot.data and gps_snapshot.data.get("has_fix"):
                frame.gps_latitude = gps_snapshot.data.get("latitude")
                frame.gps_longitude = gps_snapshot.data.get("longitude")
                frame.gps_speed_kmh = gps_snapshot.data.get("speed_kmh")
                frame.gps_heading = gps_snapshot.data.get("heading")

        # Lap timing data
        if self.lap_timing:
            lap_snapshot = self.lap_timing.get_snapshot()
            if lap_snapshot and lap_snapshot.data:
                lap_data = lap_snapshot.data
                frame.lap_number = lap_data.get("lap_number")
                frame.lap_time = lap_data.get("current_lap_time")
                frame.lap_delta = lap_data.get("delta_seconds")
                frame.sector = lap_data.get("current_sector")
                sector_times = lap_data.get("sector_times", [])
                current_sector = lap_data.get("current_sector", 0)
                if sector_times and current_sector > 0 and current_sector <= len(sector_times):
                    frame.sector_time = sector_times[current_sector - 1]
                frame.track_position = lap_data.get("track_position")
                frame.track_name = lap_data.get("track_name")

        # Fuel tracking data
        if self.fuel_tracker:
            fuel_state = self.fuel_tracker.get_state()
            if fuel_state.get('data_available'):
                frame.fuel_level_percent = fuel_state.get('fuel_level_percent')
                frame.fuel_rate_lph = fuel_state.get('fuel_rate_lph')
                frame.fuel_consumption_lap_litres = fuel_state.get('current_lap_consumption_litres')

        self.recorder.record_frame(frame)
