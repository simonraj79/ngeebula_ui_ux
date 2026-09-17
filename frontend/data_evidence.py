"""Offline source map: distinguish official public context from operational inputs."""
import streamlit as st


def render_data_evidence() -> None:
    st.subheader("Where the information comes from")
    st.write("Public transport data can describe the network. A maintenance plan also needs work orders, qualified people and approved access from the operator.")
    st.caption("Official sources reviewed 17 September 2026 · Public APIs are not connected to this prototype")
    with st.container(border=True):
        st.write("**Available publicly: station references**")
        st.write("A versioned LTA snapshot is now included: 213 station-code rows from the January 2025 station table, with source hashes and licence details. It is a checked reference snapshot, not a live feed.")
        st.caption("The station picker reconciles the local reference with this snapshot: CE1 resolves to Bayfront and DT4 Hume is included. Local-only entries remain marked as unverified. This does not assert current opening or service status, and no saved work is rewritten.")
        st.caption("Contains information from Train Station Codes and Chinese Names, accessed 17 September 2026 from LTA DataMall, made available under the Singapore Open Data Licence 1.0.")
        st.markdown("[LTA static datasets](https://datamall.lta.gov.sg/content/datamall/en/static-data.html) · [Open Data Licence](https://datamall.lta.gov.sg/content/datamall/en/SingaporeOpenDataLicence.html)")
    with st.container(border=True):
        st.write("**Available with an LTA account key: transport context**")
        st.write("Train service alerts, station crowding, passenger volumes and lift-maintenance information are available through DataMall. The maintenance feed covers station lifts; it is not a general train or track repair schedule.")
        st.markdown("[LTA dynamic datasets](https://datamall.lta.gov.sg/content/datamall/en/dynamic-data.html) · [API documentation](https://datamall.lta.gov.sg/content/dam/datamall/datasets/LTA_DataMall_API_User_Guide.pdf)")
    with st.container(border=True):
        st.write("**Needed from the operator: maintenance resources**")
        st.write("Work orders, asset condition, crew qualifications, shifts, spare parts, access permissions and release-to-service decisions were not available as public feeds in the reviewed sources. The app uses local inputs and explicitly labelled synthetic examples.")
        st.markdown("[SMRT’s published asset-management context](https://www.smrt.com.sg/getmedia/eaa6e7b1-4e78-4b53-a08e-183096ae68f0/Annex-A_Supplementary-information-to-the-Media-Release.pdf)")
    with st.expander("How to prove value in an operational pilot"):
        st.write("Run the same planning cases through the current process and the proposed tool. Record preparation, correction, review and approval time—not only computer runtime. Check completion before deadlines, accepted proposals and changes required by the planner.")
        st.write("Use observed effort and agreed costs in the savings calculator. Include integration, training and ongoing support. Public passenger data alone cannot establish avoided disruption or financial savings.")
        st.caption("This prototype is not endorsed by LTA or SMRT. Public transport data does not authorize maintenance access or certify safe operation.")
