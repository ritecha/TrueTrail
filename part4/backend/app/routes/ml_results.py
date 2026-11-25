from fastapi import APIRouter, HTTPException
import json
import os

router = APIRouter(prefix="/api/v1/ml", tags=["ML Predictions"])

# Path to outputs folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")

@router.get("/accounts")
def get_account_predictions():
    """Returns the network graph JSON with ML account predictions."""
    file_path = os.path.join(OUTPUTS_DIR, "network_graph.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Account predictions not generated yet. Run network_correlation first.")
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Filter only accounts that have ML predictions
    accounts_with_ml = [node for node in data.get("nodes", []) if node.get("ml_probability") is not None]
    
    return {
        "total_nodes": len(data.get("nodes", [])),
        "ml_analyzed_accounts": accounts_with_ml
    }

@router.get("/chains")
def get_chain_predictions():
    """Returns the fund flow analysis JSON with ML chain predictions."""
    file_path = os.path.join(OUTPUTS_DIR, "fund_flow_analysis.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Chain predictions not generated yet. Run network_correlation first.")
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return {
        "ml_chain_predictions": data.get("ml_chain_predictions", []),
        "circular_fund_flows": data.get("circular_fund_flows", [])
    }