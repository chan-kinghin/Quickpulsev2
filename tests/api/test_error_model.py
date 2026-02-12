"""Tests for ErrorResponse model."""

from src.models.errors import ErrorResponse


class TestErrorResponse:
    """Tests for ErrorResponse Pydantic model."""

    def test_error_response_with_error_code(self):
        """Test ErrorResponse serialization with error_code."""
        err = ErrorResponse(detail="Something went wrong", error_code="internal_error")
        data = err.model_dump()
        assert data["detail"] == "Something went wrong"
        assert data["error_code"] == "internal_error"

    def test_error_response_without_error_code(self):
        """Test ErrorResponse with default None error_code."""
        err = ErrorResponse(detail="Not found")
        data = err.model_dump()
        assert data["detail"] == "Not found"
        assert data["error_code"] is None

    def test_error_response_json_includes_error_code_none(self):
        """Test JSON output includes error_code even when None."""
        err = ErrorResponse(detail="Bad request")
        json_str = err.model_dump_json()
        assert "error_code" in json_str

    def test_error_response_error_code_optional(self):
        """Test error_code field is truly optional (not required)."""
        # Should not raise ValidationError when omitted
        err = ErrorResponse(detail="test")
        assert err.error_code is None
