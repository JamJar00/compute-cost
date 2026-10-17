#!/usr/bin/env python3
"""Fetch the AWS prices used by the calculator and update its data file."""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


PRICE_LIST_HOST = "https://pricing.us-east-1.amazonaws.com"
PRICE_LIST_BASE = f"{PRICE_LIST_HOST}/offers/v1.0/aws"
SPOT_ADVISOR_URL = "https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json"
REGION = "eu-west-2"
# AWS's public price list omits Fargate Spot rates; keep the existing estimate.
FARGATE_SPOT_DISCOUNT = 0.673
OUTPUT_FILE = Path(__file__).resolve().parents[1] / "src/lib/aws-prices.json"


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "compute-cost-price-updater"})
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def fetch_region_offer(service):
    index = fetch_json(f"{PRICE_LIST_BASE}/{service}/current/region_index.json")
    try:
        offer_url = index["regions"][REGION]["currentVersionUrl"]
    except KeyError as error:
        raise ValueError(f"AWS price list has no {REGION} offer for {service}") from error
    return fetch_json(f"{PRICE_LIST_HOST}{offer_url}")


def find_product(offer, description, predicate):
    matches = [
        (sku, product)
        for sku, product in offer["products"].items()
        if predicate(product.get("attributes", {}))
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one product for {description}, found {len(matches)}")
    return matches[0]


def price_dimensions(offer, sku):
    try:
        terms = offer["terms"]["OnDemand"][sku]
    except KeyError as error:
        raise ValueError(f"Missing OnDemand price terms for SKU {sku}") from error
    return [
        dimension
        for term in terms.values()
        for dimension in term["priceDimensions"].values()
    ]


def one_usd_price(offer, sku, description):
    dimensions = price_dimensions(offer, sku)
    if len(dimensions) != 1 or "USD" not in dimensions[0]["pricePerUnit"]:
        raise ValueError(f"Expected one USD price for {description}")
    return float(dimensions[0]["pricePerUnit"]["USD"])


def lambda_duration_tiers(offer):
    sku, _ = find_product(
        offer,
        "London x86 Lambda duration",
        lambda attributes: attributes.get("usagetype") == "EUW2-Lambda-GB-Second",
    )
    dimensions = price_dimensions(offer, sku)
    tiers = [
        {
            "from": int(dimension["beginRange"]),
            "upTo": (
                None
                if dimension["endRange"] == "Inf"
                else int(dimension["endRange"])
            ),
            "rate": float(dimension["pricePerUnit"]["USD"]),
        }
        for dimension in dimensions
    ]
    tiers.sort(key=lambda tier: tier["from"])
    if not tiers or tiers[0]["from"] != 0:
        raise ValueError("Lambda duration tiers are incomplete")
    return tiers


def update_prices():
    ecs = fetch_region_offer("AmazonECS")
    lambda_offer = fetch_region_offer("AWSLambda")
    ec2 = fetch_region_offer("AmazonEC2")
    spot_advisor = fetch_json(SPOT_ADVISOR_URL)

    fargate_vcpu_sku, _ = find_product(
        ecs,
        "London Fargate vCPU",
        lambda attributes: attributes.get("usagetype")
        == "EUW2-Fargate-vCPU-Hours:perCPU",
    )
    fargate_gb_sku, _ = find_product(
        ecs,
        "London Fargate memory",
        lambda attributes: attributes.get("usagetype")
        == "EUW2-Fargate-GB-Hours",
    )
    lambda_request_sku, _ = find_product(
        lambda_offer,
        "London Lambda requests",
        lambda attributes: attributes.get("usagetype") == "EUW2-Request",
    )
    ec2_sku, _ = find_product(
        ec2,
        "London Linux shared c5.large On-Demand",
        lambda attributes: (
            attributes.get("instanceType") == "c5.large"
            and attributes.get("operatingSystem") == "Linux"
            and attributes.get("tenancy") == "Shared"
            and attributes.get("preInstalledSw") == "NA"
            and attributes.get("capacitystatus") == "Used"
            and attributes.get("marketoption") == "OnDemand"
        ),
    )

    fargate_vcpu = one_usd_price(ecs, fargate_vcpu_sku, "Fargate vCPU")
    fargate_gb = one_usd_price(ecs, fargate_gb_sku, "Fargate memory")
    ec2_on_demand = one_usd_price(ec2, ec2_sku, "c5.large On-Demand")

    try:
        spot_savings_percent = spot_advisor["spot_advisor"][REGION]["Linux"][
            "c5.large"
        ]["s"]
    except KeyError as error:
        raise ValueError("AWS Spot Advisor has no London Linux c5.large data") from error
    if (
        not isinstance(spot_savings_percent, (int, float))
        or not 0 <= spot_savings_percent < 100
    ):
        raise ValueError(f"Invalid c5.large Spot Advisor savings: {spot_savings_percent}")

    prices = {
        "lastFetched": datetime.now(timezone.utc).date().isoformat(),
        "lambda": {
            "gbSecondTiers": lambda_duration_tiers(lambda_offer),
            "requestPerMillion": round(
                one_usd_price(lambda_offer, lambda_request_sku, "Lambda requests")
                * 1_000_000,
                10,
            ),
        },
        "fargate": {
            "gbHour": fargate_gb,
            "vcpuHour": fargate_vcpu,
            "spotDiscount": FARGATE_SPOT_DISCOUNT,
        },
        "ec2": {
            "c5LargeOnDemand": ec2_on_demand,
            "c5LargeSpotSavingsPercent": spot_savings_percent,
            "c5LargeSpot": ec2_on_demand * (1 - spot_savings_percent / 100),
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = OUTPUT_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(json.dumps(prices, indent=2) + "\n", encoding="utf-8")
    temporary_file.replace(OUTPUT_FILE)
    print(f"Updated {OUTPUT_FILE} with AWS prices fetched on {prices['lastFetched']}")


if __name__ == "__main__":
    update_prices()
