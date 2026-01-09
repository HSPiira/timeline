"""OpenTelemetry distributed tracing configuration"""

import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
    OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (BatchSpanProcessor,
                                            ConsoleSpanExporter)
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


class TelemetryConfig:
    """
    OpenTelemetry configuration for distributed tracing

    Features:
    - Automatic instrumentation of FastAPI, SQLAlchemy, Redis
    - Support for multiple exporters (OTLP, Jaeger, Console)
    - Request/response correlation
    - Performance monitoring
    - Error tracking

    Supported Backends:
    - Jaeger (direct or via OTLP)
    - Tempo (via OTLP)
    - Datadog (via OTLP)
    - Any OTLP-compatible backend
    """

    def __init__(self, service_name: str, service_version: str, enabled: bool = True):
        self.service_name = service_name
        self.service_version = service_version
        self.enabled = enabled
        self.tracer_provider: TracerProvider | None = None

    def setup_telemetry(
        self,
        exporter_type: str = "console",
        otlp_endpoint: str | None = None,
        jaeger_endpoint: str | None = None,
        sample_rate: float = 1.0,
    ) -> TracerProvider | None:
        """
        Initialize OpenTelemetry tracing

        Args:
            exporter_type: Type of exporter ("console", "otlp", "jaeger", "none")
            otlp_endpoint: OTLP gRPC endpoint (e.g., "http://localhost:4317")
            jaeger_endpoint: Jaeger endpoint (e.g., "localhost", port 6831)
            sample_rate: Sampling rate (0.0-1.0, default 1.0 = 100%)

        Returns:
            TracerProvider instance or None if disabled
        """
        if not self.enabled:
            logger.info("Telemetry disabled")
            return None

        try:
            # Create resource with service information
            resource = Resource(
                attributes={
                    SERVICE_NAME: self.service_name,
                    SERVICE_VERSION: self.service_version,
                    "deployment.environment": "development",  # Override from config
                }
            )

            # Create tracer provider
            self.tracer_provider = TracerProvider(resource=resource)

            # Configure exporter based on type
            if exporter_type == "console":
                # Console exporter for development/debugging
                exporter = ConsoleSpanExporter()
                logger.info("Using Console span exporter (development mode)")

            elif exporter_type == "otlp" and otlp_endpoint:
                # OTLP exporter - use TLS for https:// endpoints
                use_insecure = otlp_endpoint.startswith("http://")
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=use_insecure)
                logger.info(f"Using OTLP span exporter: {otlp_endpoint}")

            elif exporter_type == "jaeger" and jaeger_endpoint:
                # Direct Jaeger exporter
                exporter = JaegerExporter(
                    agent_host_name=jaeger_endpoint,
                    agent_port=6831,
                )
                logger.info(f"Using Jaeger span exporter: {jaeger_endpoint}:6831")

            elif exporter_type == "none":
                logger.info("Telemetry enabled but no exporter configured")
                trace.set_tracer_provider(self.tracer_provider)
                return self.tracer_provider

            else:
                logger.warning("Unknown exporter type '%s', using console", exporter_type)
                exporter = ConsoleSpanExporter()

            # Add batch span processor
            span_processor = BatchSpanProcessor(exporter)
            self.tracer_provider.add_span_processor(span_processor)

            # Set global tracer provider
            trace.set_tracer_provider(self.tracer_provider)

            logger.info(
                "OpenTelemetry initialized: service=%s, version=%s, exporter=%s",
                self.service_name,
                self.service_version,
                exporter_type,
            )

            return self.tracer_provider

        except Exception as e:
            logger.exception("Failed to initialize telemetry: %s", e)
            return None

    def instrument_fastapi(self, app: FastAPI):
        """
        Instrument FastAPI application with OpenTelemetry

        Automatically traces:
        - HTTP requests/responses
        - Request duration
        - Status codes
        - Exceptions
        """
        if not self.enabled or not self.tracer_provider:
            return

        try:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=self.tracer_provider,
                excluded_urls="/health,/metrics",  # Don't trace health checks
            )
            logger.info("FastAPI instrumentation enabled")
        except Exception as e:
            logger.error("Failed to instrument FastAPI: %s", e)

    def instrument_sqlalchemy(self, engine: AsyncEngine):
        """
        Instrument SQLAlchemy with OpenTelemetry

        Automatically traces:
        - Database queries
        - Query duration
        - Connection pool stats
        """
        if not self.enabled or not self.tracer_provider:
            return

        try:
            SQLAlchemyInstrumentor().instrument(
                engine=engine.sync_engine,  # Use sync engine for instrumentation
                tracer_provider=self.tracer_provider,
                enable_commenter=True,  # Add trace context to SQL comments
            )
            logger.info("SQLAlchemy instrumentation enabled")
        except Exception as e:
            logger.error("Failed to instrument SQLAlchemy: %s", e)

    def instrument_redis(self):
        """
        Instrument Redis client with OpenTelemetry

        Automatically traces:
        - Redis commands
        - Command duration
        - Cache hit/miss rates
        """
        if not self.enabled or not self.tracer_provider:
            return

        try:
            RedisInstrumentor().instrument(tracer_provider=self.tracer_provider)
            logger.info("Redis instrumentation enabled")
        except Exception as e:
            logger.error("Failed to instrument Redis: %s", e)

    def instrument_logging(self):
        """
        Instrument Python logging with OpenTelemetry

        Adds trace context to log records:
        - trace_id
        - span_id
        - service.name
        """
        if not self.enabled or not self.tracer_provider:
            return

        try:
            LoggingInstrumentor().instrument(
                tracer_provider=self.tracer_provider, set_logging_format=True
            )
            logger.info("Logging instrumentation enabled")
        except Exception as e:
            logger.error("Failed to instrument logging: %s", e)

    def shutdown(self):
        """Shutdown tracer provider and flush remaining spans"""
        if self.tracer_provider:
            try:
                self.tracer_provider.shutdown()
                logger.info("Telemetry shutdown complete")
            except Exception as e:
                logger.error("Error during telemetry shutdown: %s", e)


# Global telemetry instance
_telemetry: TelemetryConfig | None = None


def get_telemetry() -> TelemetryConfig | None:
    """Get global telemetry instance"""
    return _telemetry


def set_telemetry(telemetry: TelemetryConfig):
    """Set global telemetry instance"""
    global _telemetry
    _telemetry = telemetry


def get_tracer(name: str) -> trace.Tracer:
    """
    Get tracer for creating custom spans

    Usage:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("operation_name"):
            # Your code here
            pass
    """
    return trace.get_tracer(name)
