############################################################################################
# # # # # # # # # # # # # # # # # #     MD ANALYZER      # # # # # # # # # # # # # # # # # #
############################################################################################

import MDAnalysis as mda
from MDAnalysis import transformations as trans
from MDAnalysis.analysis.rdf import InterRDF

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

st.set_page_config(
    layout="wide",
)

ss = st.session_state

xyz_options = [item for item in Path(".").glob("**/*.xyz")]
xyz_options.sort()
xyz_selection = st.sidebar.selectbox(
    "Select trajectory file", xyz_options, format_func=lambda x: x.name
)

topo_options = [item for item in Path(".").glob("**/*.mol2")]
topo_options.sort()
topo_selection = st.sidebar.selectbox(
    "Select topology file", topo_options, format_func=lambda x: x.name
)

pbc_options = [item for item in Path(".").glob("**/*.pbc")]
pbc_options.sort()
pbc_selection = st.sidebar.selectbox(
    "Select pbc file", pbc_options, format_func=lambda x: x.name
)


def create_u():
    u = mda.Universe(topo_selection, xyz_selection, format="XYZ", topology_format="MOL2")
    with open(pbc_selection, "r") as f:
        box_side = float(f.read())
        u.dimensions = [box_side, box_side, box_side, 90, 90, 90]
    return u


####################################################################################################

# Calculating Radial Distribution Functions (RDFs)

rdf_check = st.sidebar.checkbox("Calculate RDFs")

if rdf_check:

    u = create_u()

    water = u.select_atoms("not resid 201")

    workflow = [
        trans.unwrap(u.atoms),
        trans.wrap(water, compound="residues"),
    ]
    u.trajectory.add_transformations(*workflow)

    rdf = InterRDF(
        u.select_atoms(f"name O"),
        u.select_atoms(f"name O"),
        nbins=500,
        range=([2.0, 9.0]),
        exclusion_block=(1, 1),
    )

    if "rdf_OO" not in st.session_state:
        st.session_state["rdf_OO"] = rdf.run(step=1)
    if st.sidebar.button("Recalculate RDFs"):
        st.session_state["rdf_OO"] = rdf.run(step=1)
    rdf_OO = st.session_state["rdf_OO"]

    fig_rdf = go.Figure()

    import os

    exp_path = (
        f"{os.path.dirname(os.path.dirname(st.__file__))}/tamagotchi/data/RDF_OO_exp.csv"
    )

    exp = pd.read_csv(exp_path)

    fig_rdf.add_trace(
        go.Scatter(
            x=exp["r (Å)"],
            y=exp["g_OO"],
            name="Experimental",
        ),
    )

    fig_rdf.add_trace(
        go.Scatter(
            x=rdf_OO.results.bins,
            y=rdf_OO.results.rdf,
            name="Calculated",
        ),
    )

    fig_rdf.update_xaxes(title_text="r (Å)")
    fig_rdf.update_yaxes(title_text="g(r) O-O")

    st.plotly_chart(fig_rdf, use_container_width=True)

####################################################################################################

# Calculating linear density

dens_check = st.sidebar.checkbox("Calculate Linear Density")

if dens_check:

    u = create_u()

    from MDAnalysis.analysis.lineardensity import LinearDensity

    ldens = LinearDensity(u.atoms, binsize=0.1)

    if "ldens" not in st.session_state:
        st.session_state["ldens"] = ldens.run()
    if st.sidebar.button("Recalculate Linear Density"):
        st.session_state["ldens"] = ldens.run()
    ldens = st.session_state["ldens"]

    fig_ldens = go.Figure()
    average = (
        ldens.results.x.mass_density
        + ldens.results.y.mass_density
        + ldens.results.z.mass_density
    ) / 3

    fig_ldens.add_trace(
        go.Scatter(
            x=ldens.results.x.hist_bin_edges,
            y=ldens.results.x.mass_density,
            name="X",
            line={
                "width": 0.5,
                "color": "red",
            },
        ),
    )
    fig_ldens.add_trace(
        go.Scatter(
            x=ldens.results.y.hist_bin_edges,
            y=ldens.results.y.mass_density,
            name="Y",
            line={
                "width": 0.5,
                "color": "green",
            },
        ),
    )
    fig_ldens.add_trace(
        go.Scatter(
            x=ldens.results.z.hist_bin_edges,
            y=ldens.results.z.mass_density,
            name="Z",
            line={
                "width": 0.5,
                "color": "blue",
            },
        ),
    )
    fig_ldens.add_trace(
        go.Scatter(
            x=ldens.results.z.hist_bin_edges,
            y=average,
            name="Average",
            line={
                "width": 3,
                "color": "black",
            },
        ),
    )
    st.plotly_chart(fig_ldens, use_container_width=True)

####################################################################################################

# Calculating Mean Squared Displacement (MSD)

msd_check = st.sidebar.checkbox("Calculate MSD and self-diffusivity")

if msd_check:

    u = create_u()

    import MDAnalysis.analysis.msd as msd

    MSD = msd.EinsteinMSD(u, select="all", msd_type="xyz", fft=True)

    if "MSD" not in st.session_state:
        st.session_state["MSD"] = MSD.run()
    if st.sidebar.button("Recalculate MSD"):
        st.session_state["MSD"] = MSD.run()
    MSD = st.session_state["MSD"]

    msd = MSD.results.timeseries

    nframes = MSD.n_frames
    timestep = 100  # this needs to be the actual time between frames
    st.write(f"Calculating MSD with a timestep of {timestep} fs")
    lagtimes = np.arange(nframes) * timestep  # make the lag-time axis

    fig_msd = make_subplots(specs=[[{"secondary_y": True}]])

    fig_msd.add_trace(
        go.Scatter(
            x=lagtimes,
            y=msd,
            name="MSD",
        ),
    )

    # Calculating self-diffusivity

    from scipy.stats import linregress

    start_time, end_time = st.slider(
        label="Select start and end time (ps):",
        min_value=int(lagtimes[0]),
        max_value=int(lagtimes[-1]),
        value=(int(lagtimes[0]), int(lagtimes[-1])),
    )
    start_index = int(start_time / timestep)
    end_index = int(end_time / timestep)

    fig_msd.add_trace(
        go.Scatter(
            x=np.arange(start_time, end_time),
            y=np.arange(start_time, end_time),
            name="slope = 1",
            line={
                "dash": "dash",
            },
        ),
        secondary_y=True,
    )
    fig_msd.update_xaxes(
        range=[start_time, end_time],
        title_text="lagtime (fs)",
        # type="log",
    )
    fig_msd.update_yaxes(
        range=[msd[start_time // timestep], msd[end_time // timestep]],
        title_text="MSD (Å^2 / fs)",
        # type="log",
    )
    fig_msd.update_yaxes(
        title_text="",
        range=[start_time, end_time],
        secondary_y=True,
        # type="log",
    )

    linear_model = linregress(lagtimes[start_index:end_index], msd[start_index:end_index])
    slope = linear_model.slope
    error = linear_model.rvalue
    # dim_fac is 3 as we computed a 3D msd with 'xyz'
    D = slope * 1 / (2 * MSD.dim_fac)
    st.write(f"Self-diffusivity coefficient: {(D*(10**-5)):.3E} m\N{SUPERSCRIPT TWO}/s")

    st.plotly_chart(fig_msd, use_container_width=True)

####################################################################################################

# Calculating dielectric constant

diel_check = st.sidebar.checkbox("Calculate Dielectric Constant")

if diel_check:

    u = create_u()

    from MDAnalysis.analysis.dielectric import DielectricConstant

    diel = DielectricConstant(u.atoms, temperature=298.15, make_whole=True)

    if "diel" not in st.session_state:
        st.session_state["diel"] = diel.run()
    if st.sidebar.button("Recalculate Dielectric Constant"):
        st.session_state["diel"] = diel.run()
    diel = st.session_state["diel"]

    st.write(f"Dielectric constant: {diel.results.eps_mean}")
