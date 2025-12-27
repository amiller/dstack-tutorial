

Dstack Tutorial: Building an DevProof “Unruggable” App

This tutorial is meant to close a gap in explaining how to use Dstack to its fullest. Dstack is designed around making applications that are “unruggable” or “dev proof” by design, in a way that is enforced by the TEE.

Why is there a gap? If you just follow the Dstack guides so far, you will NOT get a dev proof design. You will get effectively an ordinary server where you, the admin, can rug your users. This is because the easy paths leave in some kind of developer back door. Your app runs in a TEE, but still the developer can “rug”.

Writing unruggable apps is actually a really unusual way of building a system and writing code. It’s actually what smart contracts and web3 aspire to, a lot of pure solidity and DeFi explainers will cover this as their basic threat model. Though in many ways TEE is the first time we can really apply it. This is because we can apply it to far more practical code…. Most DeFi apps only have a little bit of their functionality in a smart contract. 

So, even though running arbitrary code in Dstack is really easy, we still have to think about it from this perspective to build the rest.

 Motivating example: Building a TEE oracle for a prediction market.
This tutorial will cover a couple of paradigms, but will use a main running example of an oracle system for resolving prediction markets.
We will be happy regarding TLS as an external valid source. In fact all we want is a proof that we visited a TLS.

Dev Proof concepts

	Not just about security. DevProof is something else. It’s not incompatible with reasoning about security, it’s just that in this setting the threat model is malicious behavior from the developer themselves. Going above at design time, to prove that they aren’t capable of letting you down at operation time.

	Decentralized apps. Decentralized and dev proof go together. Really about whether we rely on the dev for “availability”. This can be reasonable.

Related to non-custodial in blockchains. As a developer, just because you author an application that touches user data, doesn’t mean you’re in possession of that user data. Ability to dispose of assets.

Examples of dev proof reasoning:  
Oracle used to settle a prediction market.
	Shouldn’t be able to change how the bets are settled.
	Also availability.

Could be building a verifiable credential using zkTLS.
	Shouldn’t be able to forge.

Providing evidence you collected user consent.
	If you claim to have 10k users, can you show you collected 10k consent

	Providing evidence no user data has been exposed to risk. From the entire duration your domain was issued, no one showed it

	

Analogies of DevProofness from Smart contracts
Let’s look at some concepts of how smart contracts achieve dev proof design:
	- typically come with open source
	- compiled version on chain (codehash) can be compared with verifiable build
	- users are expected to do their own research
- practically, also rely on auditors, who audit the source code and also check the on-chain deployment 
	- by default, the underling system is immutable. However, cope by building “upgrade” mechanisms. 
	- Upgrade mechanisms too become a single point of failure, so they build limitations, on-chain “due process”.
	- even with 

0. Setting up the development environment.
	Just Docker Compose

Phala Simulator. Then attestation and KMS will work

Using the Dstack Guest SDK in Python and JS

	Running on TDX:
		Phala Cloud
		Self hosted Dstack

	Other notes: https://docs.phala.com/dstack/local-development

	Single file docker compose vs pushing to a registry. Just a matter of taste, eventually registry is needed, but experiments and tutorial demos fun to stay in self-contained 

1. How to make a Dstack application that’s “Auditable.”
	Reference values for code
	Low level attestation
	Trust-center and verification scripts
	On-chain PCCS and intel tcb versions
	We’ll provide a verification script
	We need to discuss thinking about reproducibility and reference values.

2. Using the On-chain KMS and App Auth
	Producing signed messages that are easily verifiable using on-chain tools
	Joining multiple nodes to the network

The oracle can produce signed messages that can be checked on an ethereum chain.
Set the “anyDevice” with the Phala cli and you can join with multiple nodes.
		This is a tool that automates the deployment of a contract, you can also launch the contract yourself.
Basically the verification from step 1 is now encapsulated by the KMS.

Upgrades now need to go through the contract.

3. Handling TLS
	Verification prior to use vs browsers
	Using the gateway with a custom domain
	The CT history of the domain becomes part of the audit surface
	stunnel example for TCP routing over TLS

4. Oracle finishing, hardening https
	Ocsp stapling, checking CRLs, checking CT records
	https://github.com/Gldywn/hardened-https-agent/blob/main/BACKGROUND.md
	https://github.com/Gldywn/phala-cloud-oracle-template


Advanced:

5. Encryption integrity, freshness
Using a database with encrypted records
	Encrypted data using derived key
	Integrity and freshness… ultimately for freshness we need more replication or light client
	Rollbacks and access patterns are the easiest failure modes here

6. All about Light Clients
	Making a proof about a blockchain state
	Checkpoints
Post about Helios and its use in Dstack
https://heytdep.github.io/post/31/post.html
	How do we handle versioning of light client code?

What does the demo of Heilos give?
https://helios.a16zcrypto.com/demo

	
7. Extending the AppAuth contract 
	Proof of Cloud and machine IDs.
	Upgrade policies like a pending period

8. More about handling TLS
	This tutorial will be based on the Dstack-Ingress
