"""All tests use synthetic local data; never connect to mail providers."""
import os
import tempfile
os.environ["EMAIL_FORWARDER_DATA_DIR"] = tempfile.mkdtemp(prefix="collector-tests-")
os.environ["PUBLIC_BASE_URL"] = "https://collector.test"
os.environ["URL_PREFIX"] = "/email-collector"
