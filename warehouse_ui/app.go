package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
)

type Robot struct {
	ID       int   `json:"id"`
	SpawnPos []int `json:"spawn_pos"`
}

type Task struct {
	ItemID string `json:"item_id"`
	Pos    []int  `json:"pos"`
}

type GridSize struct {
	Width  int `json:"width"`
	Height int `json:"height"`
}

type WarehouseLayout struct {
	LayoutName string   `json:"layout_name"`
	GridSize   GridSize `json:"grid_size"`
	MapData    [][]int  `json:"map_data"`
	Robots     []Robot  `json:"robots"`
	TaskPool   []Task   `json:"task_pool"`
}

type SimulationState struct {
	Running        bool      `json:"running"`
	RobotPositions [][]int   `json:"robot_positions"`
	Targets        [][]int   `json:"targets"`
	Step           int       `json:"step"`
}

type App struct {
	ctx        context.Context
	layout     *WarehouseLayout
	simState   *SimulationState
	pythonURL  string
}

func NewApp() *App {
	return &App{
		pythonURL: "http://127.0.0.1:8000",
	}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
}

func (a *App) CheckAIConnection() map[string]interface{} {
	resp, err := http.Get(a.pythonURL + "/")
	if err != nil {
		return map[string]interface{}{"connected": false, "error": err.Error()}
	}
	defer resp.Body.Close()
	return map[string]interface{}{"connected": true, "status": "AI Brain Online"}
}

func (a *App) InitAIEnv(layoutPath string) (map[string]interface{}, error) {
	absPath, _ := filepath.Abs(layoutPath)
	jsonData, _ := json.Marshal(map[string]string{"json_path": absPath})
	resp, err := http.Post(a.pythonURL+"/init_env", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	return result, nil
}

func (a *App) GetRobotAction(robotID int, currentPos []int, grid [][]int) (map[string]interface{}, error) {
	payload := map[string]interface{}{
		"robot_id":    robotID,
		"current_pos": currentPos,
		"grid":        grid,
	}
	jsonData, _ := json.Marshal(payload)
	resp, err := http.Post(a.pythonURL+"/get_action", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	return result, nil
}

func (a *App) SaveLayout(layout WarehouseLayout, filename string) error {
	data, _ := json.MarshalIndent(layout, "", "  ")
	path := filepath.Join("..", "data", "layouts", filename)
	os.MkdirAll(filepath.Dir(path), 0755)
	return os.WriteFile(path, data, 0644)
}

func (a *App) LoadLayout(filename string) (*WarehouseLayout, error) {
	path := filepath.Join("..", "data", "layouts", filename)
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var layout WarehouseLayout
	json.Unmarshal(data, &layout)
	a.layout = &layout
	return &layout, nil
}

func (a *App) GetDefaultLayout() WarehouseLayout {
	mapData := make([][]int, 20)
	for i := range mapData {
		mapData[i] = make([]int, 20)
		for j := range mapData[i] {
			if i == 0 || i == 19 || j == 0 || j == 19 {
				mapData[i][j] = 1
			}
		}
	}
	return WarehouseLayout{
		LayoutName: "new_warehouse",
		GridSize:   GridSize{Width: 20, Height: 20},
		MapData:    mapData,
		Robots:     []Robot{},
		TaskPool:   []Task{},
	}
}

func (a *App) Greet(name string) string {
	return fmt.Sprintf("Hello %s, Welcome to Warehouse MARL!", name)
}
