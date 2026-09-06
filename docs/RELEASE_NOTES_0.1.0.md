First research preview of FlowAnalysis: a local desktop application with Chinese and English interfaces.

Includes FCS import/export, hierarchical gates, conventional compensation, spectral least-squares unmixing, UMAP, t-SNE, FlowSOM, exploratory cell-cycle/proliferation models, kinetics, derived parameters, plate mapping, statistics, plot layouts, portable projects and FlowJo workspace compatibility through FlowKit.

- Both macOS and Windows builds pass the 29-test suite and a frozen-application check that runs the analysis algorithms in a separate process.
- Public FCS and spectral fixture sources and preparation instructions are in [TEST_DATA.md](https://github.com/JiaGuangshuai/FlowAnalysis/blob/main/docs/TEST_DATA.md).
- macOS: extract the ZIP and move FlowAnalysis.app to Applications. Windows: run the Setup EXE, or extract the entire portable ZIP and launch FlowAnalysis.exe.
- These packages have no paid Developer ID/Authenticode signing. Local macOS builds use ad-hoc signing; operating-system download checks may require explicit approval.
- This is a research preview, not a claim of full numerical equivalence to FlowJo or proprietary instrument software. Review fitting residuals and reference controls.
- GPL-3.0-only application; third-party notices are included. The ThirdPartySources archive and [source access notes](https://github.com/JiaGuangshuai/FlowAnalysis/blob/main/docs/THIRD_PARTY_SOURCES.md) provide upstream source references.

English is the default README; a Chinese version is linked at the top.
