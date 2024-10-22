import beaker
import pyteal as pt
from algokit_utils import DELETABLE_TEMPLATE_NAME, UPDATABLE_TEMPLATE_NAME
from beaker.consts import BOX_BYTE_MIN_BALANCE, BOX_FLAT_MIN_BALANCE
from beaker.lib.storage import BoxMapping


class UserUrl(pt.abi.NamedTuple):
    label: pt.abi.Field[pt.abi.String]
    url: pt.abi.Field[pt.abi.String]


class UserRecord(pt.abi.NamedTuple):
    name: pt.abi.Field[pt.abi.String]
    bio: pt.abi.Field[pt.abi.String]
    urls: pt.abi.Field[pt.abi.DynamicArray[UserUrl]]


class AppState:
    g_counter = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64, default=pt.Int(0), descr="For user counter"
    )
    g_fee = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(1000000),
        descr="Fee to create profile",
    )
    b_info = BoxMapping(
        key_type=pt.abi.Address,
        value_type=UserRecord,
        # prefix=pt.Bytes("i")
    )


state = AppState()

app = beaker.Application("algopass", state=state).apply(
    beaker.unconditional_create_approval, initialize_global_state=True
)

MIN_BAL = pt.Int(100000)
MAX_NAME_LEN = pt.Int(15)
MAX_BIO_LEN = pt.Int(200)
FEE_WHEN_DELETE = pt.Int(500000)


@app.external
def init_profile(
    payment: pt.abi.PaymentTransaction,
    name: pt.abi.String,
    bio: pt.abi.String,
    urls: pt.abi.DynamicArray[UserUrl],
    *,
    output: pt.abi.Bool,
) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Not(state.b_info[pt.Txn.sender()].exists()), comment="Initialized"
        ),
        pt.Assert(pt.Txn.sender() == payment.get().sender()),
        pt.Assert(
            payment.get().receiver() == pt.Global.current_application_address(),
        ),
        pt.Assert(
            payment.get().amount() == state.g_fee.get(),
            comment=f"payment must be for >= {state.g_fee.get()}",
        ),
        state.g_counter.increment(),
        pt.Assert(pt.Len(name.get()) <= MAX_NAME_LEN),
        pt.Assert(pt.Len(bio.get()) <= MAX_BIO_LEN),
        (temp := UserRecord()).set(name, bio, urls),
        state.b_info[pt.Txn.sender()].set(temp),
        output.set(pt.Int(1)),
    )


@app.external
def update_profile(
    bio: pt.abi.String,
    urls: pt.abi.DynamicArray[UserUrl],
    *,
    output: UserRecord,
) -> pt.Expr:
    return pt.Seq(
        pt.Assert(state.b_info[pt.Txn.sender()].exists(), comment="Not Exist"),
        pt.Assert(pt.Len(bio.get()) <= MAX_BIO_LEN),
        (cur_p := UserRecord()).decode(state.b_info[pt.Txn.sender()].get()),
        (keep_name := pt.abi.String()).set(cur_p.name),
        cur_p.set(keep_name, bio, urls),
        state.b_info[pt.Txn.sender()].set(cur_p),
        state.b_info[pt.Txn.sender()].store_into(output),
        # output.decode(cur_p.encode()),
    )


@app.external(read_only=True)
def get_profile(user: pt.abi.Address, *, output: UserRecord) -> pt.Expr:
    return pt.Seq(
        pt.Assert(state.b_info[user].exists(), comment="Not Exist"),
        state.b_info[user].store_into(output),
    )


@app.external
def remove_profile(*, output: pt.abi.Bool) -> pt.Expr:
    return_amount = pt.ScratchVar(pt.TealType.uint64)
    return pt.Seq(
        pt.Assert(state.b_info[pt.Txn.sender()].exists(), comment="Not Exist"),
        pt.Pop(state.b_info[pt.Txn.sender()].delete()),
        state.g_counter.decrement(),
        return_amount.store(state.g_fee.get() - FEE_WHEN_DELETE),
        _do_refund(return_amount.load()),
        # pt.InnerTxnBuilder.Execute(
        #     {
        #         pt.TxnField.type_enum: pt.TxnType.Payment,
        #         pt.TxnField.amount: return_amount.load(),
        #         pt.TxnField.receiver: pt.Txn.sender(),
        #         pt.TxnField.sender: pt.Global.current_application_address(),
        #         pt.TxnField.fee: pt.Global.min_txn_fee(),
        #     }
        # ),
        output.set(pt.Int(1)),
    )


def _do_refund(amount: pt.Expr) -> pt.Expr:
    return pt.Seq(
        pt.Assert(pt.Balance(pt.Global.current_application_address()) > amount),
        pt.InnerTxnBuilder.Begin(),
        pt.InnerTxnBuilder.SetFields(
            {
                pt.TxnField.type_enum: pt.TxnType.Payment,
                pt.TxnField.amount: amount,
                pt.TxnField.receiver: pt.Txn.sender(),
                pt.TxnField.sender: pt.Global.current_application_address(),
                pt.TxnField.fee: pt.Global.min_txn_fee(),
            }
        ),
        pt.InnerTxnBuilder.Submit(),
    )


def canculate_fee_box() -> pt.Int:
    return pt.Int(
        BOX_FLAT_MIN_BALANCE
        + (pt.abi.size_of(pt.abi.Address) * BOX_BYTE_MIN_BALANCE)
        + (pt.abi.size_of(pt.abi.String) * BOX_BYTE_MIN_BALANCE)
    )


@app.external(authorize=beaker.Authorize.only_creator())
def update_fee(fee: pt.abi.Uint64) -> pt.Expr:
    return pt.Seq(pt.Assert(fee.get() > FEE_WHEN_DELETE), state.g_fee.set(fee.get()))


@app.update(authorize=beaker.Authorize.only_creator(), bare=True)
def update() -> pt.Expr:
    return pt.Assert(
        pt.Tmpl.Int(UPDATABLE_TEMPLATE_NAME),
        comment="Check app is updatable",
    )


@app.delete(authorize=beaker.Authorize.only_creator(), bare=True)
def delete() -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Tmpl.Int(DELETABLE_TEMPLATE_NAME),
            comment="Check app is deletable",
        ),
        pt.If(
            pt.Balance(pt.Global.current_application_address()) > MIN_BAL,
            withdraw_funds(),
        ),
    )


@pt.Subroutine(pt.TealType.none)
def withdraw_funds() -> pt.Expr:
    app_bal = pt.Balance(pt.Global.current_application_address())
    return pt.Seq(
        pt.Assert(
            app_bal > MIN_BAL,
        ),
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.Payment,
                pt.TxnField.receiver: pt.Txn.sender(),
                pt.TxnField.amount: app_bal - MIN_BAL,
            }
        ),
    )


@app.external
def hello(name: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return output.set(pt.Concat(pt.Bytes("Hello, "), name.get()))
