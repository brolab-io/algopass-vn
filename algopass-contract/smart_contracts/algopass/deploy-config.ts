import * as algokit from '@algorandfoundation/algokit-utils'
import { AlgopassClient, UserRecord } from '../artifacts/algopass/client'
import algosdk, { ABITupleType, decodeAddress } from 'algosdk'
import { getAlgoNodeConfig } from '@algorandfoundation/algokit-utils'

// Below is a showcase of various deployment options you can use in TypeScript Client
export async function deploy() {
  console.log('=== Deploying Algopass ===')

  const algod = algokit.getAlgoClient(getAlgoNodeConfig('testnet', 'algod'))
  const indexer = algokit.getAlgoIndexerClient(getAlgoNodeConfig('testnet', 'indexer'))
  // const algod = algokit.getAlgoClient()
  // const indexer = algokit.getAlgoIndexerClient()
  const deployer = await algokit.mnemonicAccountFromEnvironment({ name: 'DEPLOYER', fundWith: algokit.algos(3) }, algod)
  // const deployer = await algokit.mnemonicAccount(process.env.ACCOUNT_MNEMONIC!)
  await algokit.ensureFunded(
    {
      accountToFund: deployer,
      minSpendingBalance: algokit.algos(2),
      minFundingIncrement: algokit.algos(2),
    },
    algod,
  )
  const appClient = new AlgopassClient(
    {
      resolveBy: 'creatorAndName',
      findExistingUsing: indexer,
      sender: deployer,
      creatorAddress: deployer.addr,
    },
    algod,
  )
  const isMainNet = await algokit.isMainNet(algod)

  const app = await appClient.deploy({
    allowDelete: !isMainNet,
    allowUpdate: !isMainNet,
    onSchemaBreak: isMainNet ? 'append' : 'replace',
    onUpdate: isMainNet ? 'append' : 'update',
  })

  // If app was just created fund the app account
  if (['create', 'replace'].includes(app.operationPerformed)) {
    algokit.transferAlgos(
      {
        amount: algokit.algos(0.5),
        from: deployer,
        to: app.appAddress,
      },
      algod,
    )
  }

  const method = 'hello'
  const response = await appClient.hello({ name: 'world' })
  console.log(`Called ${method} on ${app.name} (${app.appId}) with name = world, received: ${response.return}`)


  // await new Promise(r => setTimeout(r, 5000));

  const boxes = [{ appId: app.appId, name: decodeAddress(deployer.addr).publicKey }]
  const isTest = await algokit.isLocalNet(algod)
  if (isTest) {

    try {
      const box = await indexer.lookupApplicationBoxByIDandName(Number(app.appId), decodeAddress(deployer.addr).publicKey).do()
      // console.log({ box })
      // const stringTupleCodec = algosdk.ABIType.from('address');
      // // const stringTupleData = box.name;
      // // const encodedTuple = stringTupleCodec.encode(stringTupleData);
      // // console.log(encodedTuple);
      // // NX3LVM2GULOAFPBXQWBWYIPYTOVUUSTRNCXAE7VBTWERI6E6L74MAULDK4
      // const decodedTuple = stringTupleCodec.decode(box.name);
      // console.log(decodedTuple);

      const valueCodec = algosdk.ABIType.from('(string,string,(string,string)[])');
      const decoded = valueCodec.decode(box.value);

      console.log(UserRecord(decoded as any))


      // const resultGetProfile = await appClient.getProfile({ user: deployer.addr }, {
      //   boxes,
      // })
      // console.log(`Called updateProfile on ${app.name} (${app.appId}) with user = ${deployer.addr}`)
      // console.log(resultGetProfile.return)
      await new Promise(r => setTimeout(r, 2000));
      const resultUpdate = await appClient.updateProfile({
        bio: "I am a developer",
        urls: [
          ["github", "hongthaipham"],
          ["twitter", "hongthaipham"],
          ["linkedin", "hongthaipham"],
          ["email", "hongthaipro@gmail.com"]
        ]
      }, { boxes })

      console.log(`Called updateProfile on ${app.name} (${app.appId}) with user = ${deployer.addr}`)
      console.log(resultUpdate.return)

      await new Promise(r => setTimeout(r, 2000));
      const resultRemove = await appClient.removeProfile({ user: deployer.addr }, { boxes })
      console.log(`Called removeProfile on ${app.name} (${app.appId}) with user = ${deployer.addr}, received: ${resultRemove.return}`)

    } catch (error) {
      const suggestedParams = await algod.getTransactionParams().do();
      const ptxn = algosdk.makePaymentTxnWithSuggestedParamsFromObject({
        from: deployer.addr,
        suggestedParams,
        to: app.appAddress,
        amount: 1_000_000,
      });

      const resultInit = await appClient.initProfile({
        payment: ptxn, name: "John Doe",
        bio: "I am a developer", urls: [["email", ""]]
      }, { boxes })
      console.log(`Called initProfile on ${app.name} (${app.appId}) with user = ${deployer.addr}, received: ${resultInit.return}`)
      // console.log(error)
    }
  }




}
