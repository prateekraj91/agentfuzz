
import json

from app.agent import run_agent
from app.tools import STATE, reset_state

if __name__ == "__main__":
    reset_state()
    
    request = (
        "Move my 5 PM Project Meeting to 6 PM "
        "and create a reminder for 5:30 PM."
    )

    result = run_agent(request)

    print("\nASSISTANT")
    print(result["reply"])

    print("\nTOOL TRACE")
    print(json.dumps(result["trace"], indent=2))

    print("\nFINAL STATE")
    print(json.dumps(result["state"], indent=2))
