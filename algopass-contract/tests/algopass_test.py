import pytest
from algokit_utils import (
    ApplicationClient,
    ApplicationSpecification,
    EnsureBalanceParameters,
    OnCompleteCallParametersDict,
    ensure_funded,
    get_localnet_default_account,
)
from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
)
from algosdk.encoding import decode_address
from algosdk.v2client.algod import AlgodClient

from smart_contracts.algopass import contract as algopass_contract


@pytest.fixture(scope="session")
def algopass_app_spec(algod_client: AlgodClient) -> ApplicationSpecification:
    return algopass_contract.app.build(algod_client)


@pytest.fixture(scope="session")
def algopass_client(
    algod_client: AlgodClient, algopass_app_spec: ApplicationSpecification
) -> ApplicationClient:
    client = ApplicationClient(
        algod_client,
        app_spec=algopass_app_spec,
        signer=get_localnet_default_account(algod_client),
        template_values={"UPDATABLE": 1, "DELETABLE": 1},
    )
    client.create()
    ensure_funded(
        algod_client,
        EnsureBalanceParameters(
            account_to_fund=client.app_address,
            funding_source=get_localnet_default_account(algod_client),
            min_spending_balance_micro_algos=2000000,
            min_funding_increment_micro_algos=2000000,
        ),
    )

    return client


def test_init_profile(algopass_client: ApplicationClient) -> None:
    acct = get_localnet_default_account(algopass_client.algod_client)
    boxes = [(algopass_client.app_id, decode_address(acct.address))]
    sp = algopass_client.algod_client.suggested_params()
    sp.fee = sp.min_fee * 2
    pay_txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=acct.address,
            receiver=algopass_client.app_address,
            amt=1_000_000,
            sp=sp,
        ),
        signer=acct.signer,
    )

    result = algopass_client.call(
        algopass_contract.init_profile,
        transaction_parameters=OnCompleteCallParametersDict(boxes=boxes),
        payment=pay_txn,
        name="Leo Pham",
        bio="Leo Pham is a blockchain developer",
        urls=[("email", "")],
    )
    g_counter = algopass_client.get_global_state().get("g_counter")
    assert g_counter == 1
    assert result.return_value == 1


def test_update_profile(algopass_client: ApplicationClient) -> None:
    acct = get_localnet_default_account(algopass_client.algod_client)
    boxes = [(algopass_client.app_id, decode_address(acct.address))]
    result = algopass_client.call(
        algopass_contract.update_profile,
        transaction_parameters=OnCompleteCallParametersDict(boxes=boxes),
        bio="Leo Pham is a blockchain developer",
        urls=[
            ("fb", "hongthaipro"),
            ("tx", "leopham_it"),
            ("email", "hongthaipro@gmail.com"),
        ],
    )
    assert result.return_value == [
        "Leo Pham",
        "Leo Pham is a blockchain developer",
        [
            ["fb", "hongthaipro"],
            ["tx", "leopham_it"],
            ["email", "hongthaipro@gmail.com"],
        ],
    ]


def test_get_profile(algopass_client: ApplicationClient) -> None:
    acct = get_localnet_default_account(algopass_client.algod_client)
    boxes = [(algopass_client.app_id, decode_address(acct.address))]
    result = algopass_client.call(
        algopass_contract.get_profile,
        transaction_parameters=OnCompleteCallParametersDict(boxes=boxes),
        user=decode_address(acct.address),
    )
    assert result.return_value == [
        "Leo Pham",
        "Leo Pham is a blockchain developer",
        [
            ["fb", "hongthaipro"],
            ["tx", "leopham_it"],
            ["email", "hongthaipro@gmail.com"],
        ],
    ]


def test_delete_profile(algopass_client: ApplicationClient) -> None:
    acct = get_localnet_default_account(algopass_client.algod_client)
    boxes = [(algopass_client.app_id, decode_address(acct.address))]
    result = algopass_client.call(
        algopass_contract.remove_profile,
        transaction_parameters=OnCompleteCallParametersDict(boxes=boxes),
    )
    assert result.return_value == 1


# def test_decode_profile(algopass_client: ApplicationClient) -> None:
#     acct = get_localnet_default_account(algopass_client.algod_client)
#     box = algopass_client.algod_client.application_box_by_name(
#         application_id=algopass_client.app_id, box_name=decode_address(acct.address)
#     )
#     codec = abi.ABIType.from_string("(string,string,(string,string)[])")
#     # box_decoded = codec.decode(box.decode)
#     print(box.get())


# def test_encode() -> None:
#     # generate a codec from the string representation of the ABI type
#     # in this case, a tuple of two strings
#     codec = abi.ABIType.from_string("(string,string)[]")

#     # encode the value to its ABI encoding with the codec
#     to_encode = [["hello", "world"], ["bonjour", "le monde"]]
#     encoded = codec.encode(to_encode)
#     print(encoded.hex())

#     # decode the value from its ABI encoding with the codec
#     decoded = codec.decode(encoded)
#     print(decoded)  # prints ["hello", "world"]

#     # generate a codec for a uint64 array
#     uint_array_codec = abi.ABIType.from_string("uint64[]")
#     uint_array = [1, 2, 3, 4, 5]
#     encoded_array = uint_array_codec.encode(uint_array)
#     print(encoded_array.hex())

#     decoded_array = uint_array_codec.decode(encoded_array)
#     print(decoded_array)  # prints [1, 2, 3, 4, 5]


def test_says_hello(algopass_client: ApplicationClient) -> None:
    result = algopass_client.call(algopass_contract.hello, name="World")

    assert result.return_value == "Hello, World"
