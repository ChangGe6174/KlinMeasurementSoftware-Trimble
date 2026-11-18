# -*- coding: utf-8 -*-
"""串口扫描、连接与后台接收。"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import serial
from serial.tools import list_ports


class SerialService:
    def __init__(self, on_data: Callable[[bytes], None], on_error: Callable[[str], None]) -> None:
        self.on_data = on_data
        self.on_error = on_error
        self._port: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @staticmethod
    def list_ports() -> list[str]:
        ports = list(list_ports.comports())
        return [port.device for port in ports]

    @property
    def is_connected(self) -> bool:
        return self._port is not None and self._port.is_open

    def connect(
        self,
        port: str,
        baudrate: int,
        bytesize: int,
        parity: str,
        stopbits: float,
        dtr: bool,
        rts: bool,
        rtscts: bool = False,
        dsrdtr: bool = False,
        xonxoff: bool = False,
    ) -> None:
        self.disconnect()
        try:
            self._port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=0.1,
                rtscts=rtscts,
                dsrdtr=dsrdtr,
                xonxoff=xonxoff,
            )
            self._port.dtr = dtr
            self._port.rts = rts
        except Exception as exc:
            self._port = None
            raise RuntimeError(f"无法连接串口 {port}: {exc}") from exc

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
        self._port = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def clear_receive_buffer(self) -> None:
        if self._port is not None and self._port.is_open:
            self._port.reset_input_buffer()

    def get_modem_status(self) -> dict[str, bool]:
        if self._port is None or not self._port.is_open:
            return {"DTR": False, "RTS": False, "DSR": False, "CTS": False, "DCD": False, "RI": False}
        return {
            "DTR": bool(self._port.dtr),
            "RTS": bool(self._port.rts),
            "DSR": bool(self._port.dsr),
            "CTS": bool(self._port.cts),
            "CD": bool(self._port.cd),
            "RI": bool(self._port.ri),
        }

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._port is None or not self._port.is_open:
                    break
                data = self._port.read(self._port.in_waiting or 1)
                if data:
                    self.on_data(data)
            except Exception as exc:
                if not self._stop_event.is_set():
                    self.on_error(str(exc))
                break
