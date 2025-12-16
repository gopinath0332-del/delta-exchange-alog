
import inspect
import delta_rest_client
from delta_rest_client import DeltaRestClient

print("Delta Rest Client Location:", delta_rest_client.__file__)
print("\nInspect place_order:")
try:
    print(inspect.signature(DeltaRestClient.place_order))
except Exception as e:
    print(f"Could not inspect signature: {e}")

# Check for Enums in the module
print("\nAttributes in delta_rest_client:")
for name in dir(delta_rest_client):
    if not name.startswith("_"):
        print(name)
