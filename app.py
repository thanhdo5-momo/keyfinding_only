from flask import Flask, render_template, request, jsonify
import pandas as pd
import os

app = Flask(__name__)

# Cache the dataframe globally
_df_cache = None

def get_dataframe():
    global _df_cache
    if _df_cache is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Try common locations relative to this file; useful if run from different CWDs
        candidate_paths = [
            os.path.join(base_dir, "raw.xlsx"),
            os.path.join(os.path.dirname(base_dir), "raw.xlsx"),
        ]

        for file_path in candidate_paths:
            if os.path.exists(file_path):
                _df_cache = pd.read_excel(file_path)
                break
        else:
            raise FileNotFoundError(
                f"raw.xlsx not found. Tried: {candidate_paths}"
            )
    return _df_cache

def load_issue_data(selected_users=None, selected_campaign_types=None, selected_segments=None):
    # Use relative path from dashboard folder to workspace data
    df = get_dataframe().copy()

    # Normalize NaN/NA so JSON stays valid
    df = df.where(pd.notnull(df), None)

    # Filter by selected users if provided and not empty
    if selected_users and len(selected_users) > 0:
        df = df[df['User'].isin(selected_users)]

    # Filter by selected campaign types if provided and not empty
    if selected_campaign_types and len(selected_campaign_types) > 0:
        df = df[df['Type'].isin(selected_campaign_types)]

    # Filter by selected user segments if provided and not empty
    if selected_segments and len(selected_segments) > 0:
        df = df[df['User Segment'].isin(selected_segments)]

    # Clean issue name (remove code prefix)
    def clean_issue_name(issue):
        if pd.isna(issue):
            return issue
        parts = str(issue).split(' ', 1)
        return parts[1] if len(parts) > 1 else parts[0]

    df['Issue_Clean'] = df['Issue'].apply(clean_issue_name)

    # Clean action name
    def clean_action_name(action):
        if pd.isna(action) or str(action).strip() == '':
            return 'No Action'
        return str(action).strip()

    df['Action_Clean'] = df['action_1'].apply(clean_action_name)

    # Custom phase order
    phase_order = [
        "Cross-cutting",
        "Phase 1: Before Payment",
        "Phase 2: During Payment",
        "Phase 3: After Payment"
    ]

    # Get all unique users for filter
    all_users = sorted(df['User'].dropna().unique().tolist())
    all_users.remove('User') if 'User' in all_users else None

    # Get all unique campaign types for filter
    all_campaign_types = sorted(df['Type'].dropna().unique().tolist())
    all_campaign_types.remove('Type') if 'Type' in all_campaign_types else None

    # Get all unique user segments for filter
    all_segments = sorted(df['User Segment'].dropna().unique().tolist())
    all_segments.remove('User Segment') if 'User Segment' in all_segments else None

    # Get all unique actions
    all_actions = sorted(df['Action_Clean'].unique())

    # Build pivot structure: {action: {phase: [issues with counts]}}
    pivot_data = {}

    for action in all_actions:
        pivot_data[action] = {}
        action_df = df[df['Action_Clean'] == action]

        for phase in phase_order:
            phase_df = action_df[action_df['Phase'] == phase]
            if not phase_df.empty:
                # Group by Issue within this Action+Phase
                issue_counts = (
                    phase_df.groupby(['Issue', 'Issue_Clean'])['Finding']
                    .nunique()
                    .reset_index(name='Finding_Count')
                    .sort_values('Finding_Count', ascending=False)
                )
                pivot_data[action][phase] = issue_counts.to_dict('records')
            else:
                pivot_data[action][phase] = []

    # Build detail map for modal: (Action, Issue) -> findings
    detail_map = {}
    for _, row in df.iterrows():
        action = row.get('action_1', 'No Action')
        issue = row.get('Issue', '')
        key = f"{action}|||{issue}"
        if key not in detail_map:
            detail_map[key] = []
        detail_map[key].append({
            "finding": row.get('Finding', ''),
            "phase": row.get('Phase', ''),
            "user": row.get('User', ''),
            "issue_explanation": row.get('Issue_Explanation', ''),
            "action_explanation": row.get('action_1_explanation', ''),
            "action_confidence": row.get('action_1_conf', ''),
            "issue_confidence": row.get('Confidence_Score', ''),
            "campaign_type": row.get('Type', ''),
            "user_segment": row.get('User Segment', ''),
            "reference": row.get('Reference', '')
        })

    return (
        pivot_data,
        phase_order,
        all_actions,
        all_users,
        all_campaign_types,
        all_segments,
        detail_map
    )

@app.route('/')
def index():
    (
        pivot_data,
        phase_order,
        all_actions,
        all_users,
        all_campaign_types,
        all_segments,
        detail_map
    ) = load_issue_data()
    return render_template('index.html',
                         pivot_data=pivot_data,
                         phase_order=phase_order,
                         all_actions=all_actions,
                         all_users=all_users,
                         all_campaign_types=all_campaign_types,
                         all_segments=all_segments,
                         detail_map=detail_map)

@app.route('/api/filter', methods=['POST'])
def filter_data():
    data = request.get_json()
    selected_users = data.get('users', [])
    selected_campaign_types = data.get('campaign_types', [])
    selected_segments = data.get('segments', [])

    (
        pivot_data,
        phase_order,
        all_actions,
        all_users,
        all_campaign_types,
        all_segments,
        detail_map
    ) = load_issue_data(selected_users, selected_campaign_types, selected_segments)

    return jsonify({
        'pivot_data': pivot_data,
        'phase_order': phase_order,
        'all_actions': all_actions,
        'all_users': all_users,
        'all_campaign_types': all_campaign_types,
        'all_segments': all_segments,
        'detail_map': detail_map
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
