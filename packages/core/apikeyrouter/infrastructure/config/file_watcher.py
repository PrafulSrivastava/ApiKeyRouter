"""File watcher for configuration hot reload."""

import asyncio
import contextlib
import threading
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.infrastructure.config.file_loader import ConfigurationError
from apikeyrouter.infrastructure.config.manager import ConfigurationManager


class ConfigurationFileHandler(FileSystemEventHandler):
    """File system event handler for configuration files."""

    def __init__(
        self,
        config_manager: ConfigurationManager,
        config_file_path: Path,
        debounce_seconds: float = 1.0,
        observability_manager: ObservabilityManager | None = None,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Initialize configuration file handler.

        Args:
            config_manager: ConfigurationManager instance to reload configuration.
            config_file_path: Path to the configuration file being watched.
            debounce_seconds: Debounce delay in seconds to prevent rapid reloads.
            observability_manager: Optional ObservabilityManager for logging.
            event_loop: Event loop to schedule async tasks. If None, gets current loop.
        """
        self._config_manager = config_manager
        self._config_file_path = config_file_path
        self._debounce_seconds = debounce_seconds
        self._observability = observability_manager
        self._event_loop = event_loop

        # Debouncing state - use threading primitives for cross-thread coordination
        self._reload_task: asyncio.Task[None] | None = None
        self._reload_lock = threading.Lock()
        self._pending_reload = False

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification event.

        Args:
            event: File system event.
        """
        # Only handle events for the configuration file
        if event.is_directory:
            return

        event_path = Path(event.src_path)
        if event_path.resolve() != self._config_file_path.resolve():
            return

        # Schedule reload with debouncing
        # Since we're in a different thread, use run_coroutine_threadsafe
        loop = self._event_loop
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop available, can't schedule reload
                return

        if loop.is_running():
            # Schedule the coroutine in the event loop
            asyncio.run_coroutine_threadsafe(self._debounced_reload(), loop)
        else:
            # If loop is not running, can't schedule
            return

    async def _debounced_reload(self) -> None:
        """Reload configuration with debouncing.

        Cancels any pending reload and schedules a new one after debounce delay.
        """
        # Cancel any pending reload task
        with self._reload_lock:
            if self._reload_task and not self._reload_task.done():
                self._reload_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._reload_task

            # Schedule new reload after debounce delay
            self._reload_task = asyncio.create_task(self._reload_after_delay())

    async def _reload_after_delay(self) -> None:
        """Wait for debounce delay and then reload configuration."""
        await asyncio.sleep(self._debounce_seconds)

        try:
            # Log file change detected
            if self._observability:
                await self._observability.log(
                    level="INFO",
                    message="Configuration file change detected, reloading...",
                    context={
                        "config_file": str(self._config_file_path),
                        "debounce_seconds": self._debounce_seconds,
                    },
                )

            # Reload configuration
            await self._config_manager.reload_configuration()

            # Log successful reload
            if self._observability:
                await self._observability.log(
                    level="INFO",
                    message="Configuration reloaded successfully from file",
                    context={
                        "config_file": str(self._config_file_path),
                    },
                )
                await self._observability.emit_event(
                    event_type="configuration_file_reloaded",
                    payload={
                        "config_file": str(self._config_file_path),
                    },
                    metadata={},
                )

        except ConfigurationError as e:
            # Log reload failure
            if self._observability:
                await self._observability.log(
                    level="ERROR",
                    message="Configuration reload failed",
                    context={
                        "config_file": str(self._config_file_path),
                        "error": str(e),
                    },
                )
        except Exception as e:
            # Log unexpected error
            if self._observability:
                await self._observability.log(
                    level="ERROR",
                    message="Unexpected error during configuration reload",
                    context={
                        "config_file": str(self._config_file_path),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )


class ConfigurationFileWatcher:
    """File watcher for configuration hot reload.

    Watches configuration files for changes and automatically reloads
    configuration when files are modified. Includes debouncing to prevent
    rapid reloads.
    """

    def __init__(
        self,
        config_manager: ConfigurationManager,
        config_file_path: str | Path,
        debounce_seconds: float = 1.0,
        observability_manager: ObservabilityManager | None = None,
    ) -> None:
        """Initialize configuration file watcher.

        Args:
            config_manager: ConfigurationManager instance to reload configuration.
            config_file_path: Path to the configuration file to watch.
            debounce_seconds: Debounce delay in seconds to prevent rapid reloads.
            observability_manager: Optional ObservabilityManager for logging.
        """
        self._config_manager = config_manager
        self._config_file_path = Path(config_file_path)
        self._debounce_seconds = debounce_seconds
        self._observability = observability_manager

        # Watchdog observer
        self._observer: Observer | None = None
        self._handler: ConfigurationFileHandler | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Start watching the configuration file.

        Raises:
            RuntimeError: If watcher is already started.
        """
        if self._observer is not None and self._observer.is_alive():
            raise RuntimeError("File watcher is already started")

        # Get or create event loop
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, will create one when needed
            self._event_loop = None

        # Create event handler
        self._handler = ConfigurationFileHandler(
            config_manager=self._config_manager,
            config_file_path=self._config_file_path,
            debounce_seconds=self._debounce_seconds,
            observability_manager=self._observability,
            event_loop=self._event_loop,
        )

        # Create observer
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            path=str(self._config_file_path.parent),
            recursive=False,
        )

        # Start observer
        self._observer.start()

        # Log watcher started
        if self._observability:
            # Note: This is a sync method, so we can't await async methods here
            # Logging will happen in the async handler when file changes are detected
            pass

    def stop(self) -> None:
        """Stop watching the configuration file."""
        if self._observer is not None and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5.0)  # Wait up to 5 seconds for cleanup
            self._observer = None
            self._handler = None

    def is_watching(self) -> bool:
        """Check if watcher is currently watching.

        Returns:
            True if watcher is active, False otherwise.
        """
        return self._observer is not None and self._observer.is_alive()

    def __enter__(self) -> "ConfigurationFileWatcher":
        """Context manager entry.

        Returns:
            Self for use in with statement.
        """
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit.

        Args:
            exc_type: Exception type if any.
            exc_val: Exception value if any.
            exc_tb: Exception traceback if any.
        """
        self.stop()

