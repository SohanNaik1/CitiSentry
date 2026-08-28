import json
import os
import jsonschema
from jsonschema import Draft7Validator
import copy

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def validate_schema(schema_path, payload_path, expect_success=True):
    schema = load_json(schema_path)
    payload = load_json(payload_path)
    
    # We validate strictly using Draft7Validator and check format as well
    validator = Draft7Validator(schema, format_checker=jsonschema.draft7_format_checker)
    
    if isinstance(payload, list):
        all_passed = True
        for idx, item in enumerate(payload):
            errors = list(validator.iter_errors(item))
            if expect_success and errors:
                print(f"FAIL: {payload_path} at index {idx} has errors:")
                for e in errors:
                    print(f"  - {e.message}")
                all_passed = False
            elif not expect_success and not errors:
                print(f"FAIL: {payload_path} at index {idx} was expected to fail but passed.")
                all_passed = False
        
        if expect_success and all_passed:
            print(f"PASS: {payload_path} (list of {len(payload)} items) is valid.")
            return True
        elif not expect_success and all_passed:
            return True
        return all_passed
    else:
        errors = list(validator.iter_errors(payload))
        
        if expect_success:
            if errors:
                print(f"FAIL: {payload_path} should be valid but has errors:")
                for e in errors:
                    print(f"  - {e.message}")
                return False
            else:
                print(f"PASS: {payload_path} is valid.")
                return True
        else:
            if errors:
                print(f"PASS: Invalid payload correctly caught. Error: {errors[0].message}")
                return True
            else:
                print(f"FAIL: Expected invalid payload to fail validation, but it passed.")
                return False

def test_intentional_failures(schema_path, payload_path):
    print(f"\n--- Testing intentional failures for {os.path.basename(schema_path)} ---")
    schema = load_json(schema_path)
    valid_payload = load_json(payload_path)
    
    validator = Draft7Validator(schema, format_checker=jsonschema.draft7_format_checker)
    
    all_passed = True
    
    if "camera_node" in schema_path:
        # Invalid Lat
        bad_payload = valid_payload.copy()
        bad_payload["lat"] = 95.0
        errors = list(validator.iter_errors(bad_payload))
        if not errors:
            print("FAIL: Expected latitude validation to fail.")
            all_passed = False
        else:
            print("PASS: Caught invalid latitude (> 90.0).")
            
        # Invalid Camera ID
        bad_payload = valid_payload.copy()
        bad_payload["camera_id"] = "CAM-12"
        errors = list(validator.iter_errors(bad_payload))
        if not errors:
            print("FAIL: Expected camera_id pattern validation to fail.")
            all_passed = False
        else:
            print("PASS: Caught invalid camera_id pattern.")
            
    elif "telemetry_event" in schema_path:
        # Invalid confidence
        bad_payload = copy.deepcopy(valid_payload)
        bad_payload["license_plate"]["confidence"] = 1.5
        errors = list(validator.iter_errors(bad_payload))
        if not errors:
            print("FAIL: Expected confidence validation to fail.")
            all_passed = False
        else:
            print("PASS: Caught invalid confidence (> 1.0).")
            
    elif "alert_event" in schema_path:
        # Invalid enum
        bad_payload = valid_payload.copy()
        bad_payload["severity"] = "LOW"
        errors = list(validator.iter_errors(bad_payload))
        if not errors:
            print("FAIL: Expected severity enum validation to fail.")
            all_passed = False
        else:
            print("PASS: Caught invalid severity enum.")
            
    return all_passed


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    schemas_dir = os.path.join(base_dir, "schemas")
    payloads_dir = os.path.join(base_dir, "sample_payloads")
    scenarios_dir = os.path.join(base_dir, "..", "services", "edge-simulator", "scenarios")
    
    schema_payload_pairs = [
        ("camera_node.schema.json", "camera_node.sample.json"),
        ("telemetry_event.schema.json", "telemetry_event.sample.json"),
        ("alert_event.schema.json", "alert_event.sample.json")
    ]
    
    scenario_files = [
        "scenario_1_pursuit.json",
        "scenario_2_ambiguity.json",
        "scenario_3_cloned.json"
    ]
    
    all_success = True
    
    print("--- Validating valid sample payloads ---")
    for schema_file, payload_file in schema_payload_pairs:
        schema_path = os.path.join(schemas_dir, schema_file)
        payload_path = os.path.join(payloads_dir, payload_file)
        
        if not validate_schema(schema_path, payload_path, expect_success=True):
            all_success = False
            
    for schema_file, payload_file in schema_payload_pairs:
        schema_path = os.path.join(schemas_dir, schema_file)
        payload_path = os.path.join(payloads_dir, payload_file)
        if not test_intentional_failures(schema_path, payload_path):
            all_success = False
            
    print("\n--- Validating scenario payloads ---")
    if os.path.exists(scenarios_dir):
        for scenario_file in scenario_files:
            schema_path = os.path.join(schemas_dir, "telemetry_event.schema.json")
            payload_path = os.path.join(scenarios_dir, scenario_file)
            if os.path.exists(payload_path):
                if not validate_schema(schema_path, payload_path, expect_success=True):
                    all_success = False
            else:
                print(f"Warning: Scenario file not found: {payload_path}")
    else:
         print(f"Warning: Scenarios directory not found: {scenarios_dir}")
            
    if all_success:
        print("\nAll validation tests PASSED.")
        exit(0)
    else:
        print("\nSome validation tests FAILED.")
        exit(1)

if __name__ == "__main__":
    main()
