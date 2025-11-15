"""UI controller for serving HTML pages."""
from pathlib import Path

from classy_fastapi.decorators import get
from classy_fastapi.routable import Routable
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator
from neuroglia.mvc import ControllerBase
from neuroglia.mvc.controller_base import generate_unique_id_function


class UIController(ControllerBase):
    """Controller for UI pages."""

    def __init__(
        self,
        service_provider: ServiceProviderBase,
        mapper: Mapper,
        mediator: Mediator,
    ):
        # Store DI services first
        self.service_provider = service_provider
        self.mapper = mapper
        self.mediator = mediator
        self.name = "UI"

        # Get absolute path to static directory where Parcel builds the HTML
        # From src/ui/controllers/ui_controller.py -> ../../../../static
        self.static_dir = Path(__file__).parent.parent.parent.parent / "static"

        # Call Routable.__init__ directly with empty prefix for root routes
        Routable.__init__(
            self,
            prefix="",  # Empty prefix for root routes
            tags=["UI"],
            generate_unique_id_function=generate_unique_id_function,
        )

    @get("/", response_class=HTMLResponse)
    async def index(self, request: Request) -> FileResponse:
        """Serve the main application page (built by Parcel)."""
        index_path = self.static_dir / "index.html"

        return FileResponse(index_path, media_type="text/html")
